"""Drive ``rez build`` for one recipe target and hand the repository to the pack stage.

The wrapper compensates for three measured rez-next 0.3.10 gaps:

* ``rez build`` has no ``--repository`` flag, so the sibling ``platform/`` and
  ``arch/`` system packages are materialised into a bootstrap repository and
  published through ``REZ_PACKAGES_PATH``.
* the plain build path does not copy ``package.py``, so the pinned definition is
  copied byte-for-byte into the package root.
* only the exit code crosses back from the subprocess, so a non-empty payload is
  asserted explicitly.
"""

from __future__ import annotations

import ast
import json
import os
import platform as host_platform
import shutil
import subprocess
from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from tools import build_bundle
from tools.vx_rez_build import bootstrap

BUILD_SYSTEM_FILENAME = "build.py"

#: Only the rez-next binary implements the ``build`` subcommand the wrapper needs.
#: ``rez-next`` is preferred because the name is unambiguous: a legacy pip
#: installation of ``rez`` 3.x also owns the ``rez`` name but has no
#: ``--build-system`` flag, so it would fail with an unrecognised argument
#: instead of reporting the missing rez-next build interface.
REZ_EXECUTABLE_NAMES = ("rez-next", "rez")

#: Rez reports the host arch as ``amd64``; the VX package family is ``arch-x86_64``.
_HOST_ARCH_ALIASES = {"amd64": "x86_64", "x64": "x86_64", "arm64": "arm_64", "aarch64": "arm_64"}
_HOST_PLATFORM_ALIASES = {"darwin": "osx", "windows": "windows", "linux": "linux"}


class BuildError(RuntimeError):
    """A ``rez build`` cannot be run without violating the published contract."""


def load_definition(path: Path) -> dict:
    """Load and validate the portable recipe with the existing bundle validator."""
    return build_bundle.load_definition(path)


def host_triple() -> tuple[str, str]:
    """Report the host as VX (platform, arch) families."""
    system = host_platform.system().lower()
    machine = host_platform.machine().lower()
    platform = _HOST_PLATFORM_ALIASES.get(system, system)
    arch = _HOST_ARCH_ALIASES.get(machine, machine)
    return platform, arch


def _select_target(definition: dict, triple: str) -> dict:
    for target in definition["targets"]:
        if target["triple"] == triple:
            return target
    for target in definition["unsupported_targets"]:
        if target["triple"] == triple:
            raise BuildError(f"target {triple!r} is unsupported: {target['reason']}")
    raise BuildError(f"target {triple!r} is not declared by the bundle definition")


def _assert_native_target(target: dict) -> None:
    """Refuse to cross-build: the target must match the host."""
    native = host_triple()
    if native != (target["platform"], target["arch"]):
        raise BuildError(
            "rez build requires the declared native target: "
            f"wanted {target['platform']}/{target['arch']}, got {native[0]}/{native[1]}"
        )


def validate_package_definition(package_source: bytes, *, filename: str = "package.py") -> None:
    """Require one unambiguous named script, with no build-command override."""
    try:
        module = ast.parse(package_source, filename=filename)
    except (SyntaxError, ValueError) as error:
        raise BuildError(f"package definition contains invalid Python syntax: {error}") from error

    bindings = []
    for node in ast.walk(module):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bindings.append((node.id, node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bindings.append((node.name, node))
        elif isinstance(node, ast.alias):
            bindings.append((node.asname or node.name.split(".")[0], node))
    if any(name == "build_command" for name, _ in bindings):
        raise BuildError("package definition must not override the script with build_command")
    declarations = [node for name, node in bindings if name == "build_system"]
    if not declarations:
        raise BuildError("package definition must declare build_system")
    if len(declarations) != 1:
        raise BuildError("package definition must declare build_system exactly once")
    for statement in module.body:
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and statement.targets[0] is declarations[0]
        ):
            value = statement.value
            if not isinstance(value, ast.Constant) or type(value.value) is not str:
                raise BuildError("package definition build_system must be a literal string")
            if value.value != BUILD_SYSTEM_FILENAME:
                raise BuildError(
                    f"package definition build_system must be {BUILD_SYSTEM_FILENAME!r}"
                )
            return
    raise BuildError("package definition build_system must be one literal string assignment")


def _write_system_packages(repository: Path, target: dict) -> Path:
    """Materialise the sibling system packages rez needs to resolve the variant."""
    for family in ("platform", "arch"):
        root = repository / family / target[family]
        root.mkdir(parents=True, exist_ok=True)
        root.joinpath("package.py").write_text(
            f"name = {family!r}\nversion = {target[family]!r}\n",
            encoding="utf-8",
            newline="\n",
        )
    return repository


def _build_environment(
    *,
    base: dict[str, str],
    bootstrap_repository: Path,
    target: dict,
    triple: str,
    recipe_path: Path,
    extra_paths: Iterable[Path] = (),
) -> dict[str, str]:
    """Prepare the rez parent environment; the staged bootstrap restores the child."""
    environment = dict(base)
    path_entries = [str(path) for path in extra_paths]
    existing = environment.get("PATH")
    if existing:
        path_entries.append(existing)
    if path_entries:
        environment["PATH"] = os.pathsep.join(path_entries)

    # rez-next reads these but never sets them; unset they silently default to
    # the host, so they must be derived from the recipe target explicitly.
    environment["REZ_BUILD_TARGET_PLATFORM"] = target["platform"]
    environment["REZ_BUILD_TARGET_ARCH"] = target["arch"]
    environment["REZ_BUILD_TARGET_OS"] = _target_os(target["platform"])
    environment["REZ_PACKAGES_PATH"] = str(bootstrap_repository)
    environment["VX_BUILD_TRIPLE"] = triple
    # The script runs from a temporary copy, so recipe paths must be absolute.
    environment["VX_BUILD_RECIPE"] = str(recipe_path.resolve())
    return environment


def _stage_build_source(
    source: Path, destination: Path, package_source: Path, environment: dict[str, str]
) -> Path:
    """Freeze the source and carry only explicit environment keys through env_clear."""
    if not (source / BUILD_SYSTEM_FILENAME).is_file():
        raise BuildError(f"build script is missing: {source / BUILD_SYSTEM_FILENAME}")
    for reserved in (bootstrap.CONTEXT_FILENAME, bootstrap.SCRIPT_FILENAME):
        if (source / reserved).exists():
            raise BuildError(f"build source uses reserved bootstrap file: {reserved}")
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    destination.joinpath("package.py").write_bytes(package_source.read_bytes())
    destination.joinpath(BUILD_SYSTEM_FILENAME).rename(destination / bootstrap.SCRIPT_FILENAME)
    destination.joinpath(BUILD_SYSTEM_FILENAME).write_bytes(Path(bootstrap.__file__).read_bytes())
    context = {key: environment[key] for key in bootstrap.ENVIRONMENT_KEYS if key in environment}
    destination.joinpath(bootstrap.CONTEXT_FILENAME).write_text(
        json.dumps(context), encoding="utf-8", newline="\n"
    )
    return destination


def _target_os(target_platform: str) -> str:
    return {"windows": "windows", "osx": "macos", "linux": "linux"}.get(
        target_platform, target_platform
    )


def _assert_payload(variant_root: Path) -> None:
    payload = variant_root / "payload"
    if not payload.is_dir():
        raise BuildError(f"build produced no payload directory: {payload}")
    entries = list(payload.rglob("*"))
    if not entries:
        raise BuildError(f"build produced an empty payload: {payload}")
    if not any(entry.is_file() for entry in entries):
        raise BuildError(f"build payload contains no regular files: {payload}")


def build_variant(
    definition: dict,
    triple: str,
    output_directory: Path,
    *,
    metadata_directory: Path | None = None,
    sdk_executable: Path | None = None,
    rez_executable: Path | None = None,
    repositories: Iterable[Path] = (),
    source_directory: Path | None = None,
) -> Path:
    """Build one target with ``rez build`` and return the produced repository.

    The returned repository is ready for the pack stage: it holds the variant
    payload, the pinned ``package.py`` and the sibling system packages, but is
    not yet archived.
    """
    build_bundle.validate_definition(definition)
    target = _select_target(definition, triple)
    _assert_native_target(target)

    recipe_directory = (metadata_directory or Path.cwd()).resolve()
    package_source = build_bundle._read_package_definition(definition, recipe_directory)
    # Reject a silently no-op build system before invoking rez at all.
    validate_package_definition(package_source)

    tool, version = definition["tool"], definition["version"]
    with pack_stage_temporary() as work:
        pinned = work / "package.py"
        pinned.write_bytes(package_source)
        plan = build_bundle._installation_plan(
            pinned, definition, target, sdk_executable, repositories
        )

        repository = work / "repository"
        repository.mkdir()
        # rez build resolves variants through REZ_PACKAGES_PATH, so the sibling
        # system packages are staged in a bootstrap repository first; they are
        # also copied into the published repository below.
        bootstrap = _write_system_packages(work / "bootstrap", target)

        package_root = build_bundle._planned_directory(repository, plan["package_relative_path"])
        package_root.mkdir(parents=True)
        # The plain rez-next build path does not copy package.py; only its
        # release path does, so the wrapper does it here.
        package_root.joinpath("package.py").write_bytes(package_source)

        variant_root = build_bundle._planned_directory(repository, plan["variant_relative_path"])
        variant_root.mkdir(parents=True)

        source = source_directory or recipe_directory
        _run_rez_build(
            source=source,
            repository=repository,
            bootstrap_repository=bootstrap,
            package_source=pinned,
            target=target,
            triple=triple,
            recipe_path=recipe_directory / "recipe.json",
            rez_executable=rez_executable,
        )
        _assert_payload(variant_root)
        _write_system_packages(repository, target)

        output_directory = Path(output_directory)
        output_directory.mkdir(parents=True, exist_ok=True)
        result = output_directory / f"{tool}-{version}-{triple}.repository"
        if result.exists():
            shutil.rmtree(result)
        shutil.copytree(repository, result)
    return result


def _run_rez_build(
    *,
    source: Path,
    repository: Path,
    bootstrap_repository: Path,
    package_source: Path,
    target: dict,
    triple: str,
    recipe_path: Path,
    rez_executable: Path | None,
) -> None:
    executable = rez_executable or _resolve_rez_executable()
    environment = _build_environment(
        base=os.environ.copy(),
        bootstrap_repository=bootstrap_repository,
        target=target,
        triple=triple,
        recipe_path=recipe_path,
        extra_paths=[Path(executable).parent],
    )
    staged_source = _stage_build_source(
        source, package_source.parent / "source", package_source, environment
    )
    command = [
        str(executable),
        "build",
        str(staged_source),
        "--install",
        "--prefix",
        str(repository),
        "--build-system",
        BUILD_SYSTEM_FILENAME,
    ]
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3600,
            cwd=package_source.parent,
            env=environment,
            stdin=subprocess.DEVNULL,
            shell=False,
        )
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "").strip()[:2000]
        raise BuildError(f"rez build failed with exit code {error.returncode}: {detail}") from error
    except (OSError, subprocess.SubprocessError) as error:
        raise BuildError(f"rez build failed: {error}") from error


def _resolve_rez_executable() -> Path:
    configured = os.environ.get("VX_REZ_EXECUTABLE")
    if configured:
        return Path(configured)
    for name in REZ_EXECUTABLE_NAMES:
        found = shutil.which(name)
        if found:
            return Path(found)
    raise BuildError(
        "the rez-next executable is required; install rez-next 0.3.10 "
        "(cargo install rez-next --locked) or set VX_REZ_EXECUTABLE"
    )


@contextmanager
def pack_stage_temporary():
    with TemporaryDirectory(prefix="vx-rez-build-") as temporary:
        yield Path(temporary).resolve()
