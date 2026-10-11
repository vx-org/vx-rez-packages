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
import os
import platform as host_platform
import shutil
import subprocess
from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from tools import build_bundle

BUILD_SYSTEM_FILENAME = "build.py"
FORBIDDEN_BUILD_SYSTEMS = frozenset({"custom"})

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
    """Reject a ``package.py`` whose build system rez-next would silently ignore.

    rez-next resolves any unrecognised build system to ``Custom(<value>)``, and
    ``custom`` degenerates to a copy-only build in which the script never runs.
    A silent no-op build looks like a successful release, so it is refused here
    rather than caught in review.
    """
    try:
        module = ast.parse(package_source, filename=filename)
    except (SyntaxError, ValueError) as error:
        raise BuildError(f"package definition contains invalid Python syntax: {error}") from error

    for statement in module.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target, value = statement.targets[0], statement.value
        if not (isinstance(target, ast.Name) and target.id == "build_system"):
            continue
        if not isinstance(value, ast.Constant) or type(value.value) is not str:
            raise BuildError("package definition build_system must be a literal string")
        declared = value.value
        if declared in FORBIDDEN_BUILD_SYSTEMS:
            raise BuildError(
                f"build_system {declared!r} degenerates to a copy-only build in rez-next; "
                f"use {BUILD_SYSTEM_FILENAME!r} instead"
            )
        return
    raise BuildError("package definition must declare build_system")


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
    """Build the child environment, restoring what rez-next's clearing would strip."""
    environment = dict(base)
    # rez-next clears the child environment before applying the script's own; on
    # Windows that leaves no PATH at all, so shelling out to 7z/git/tar fails.
    path_entries = [str(path) for path in (*extra_paths, *[])]
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
    command = [
        str(executable),
        "build",
        str(source),
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
    found = shutil.which("rez")
    if not found:
        raise BuildError(
            "the rez executable is required; install rez-next 0.3.10 "
            "(cargo install rez-next --locked) or set VX_REZ_EXECUTABLE"
        )
    return Path(found)


@contextmanager
def pack_stage_temporary():
    with TemporaryDirectory(prefix="vx-rez-build-") as temporary:
        yield Path(temporary).resolve()
