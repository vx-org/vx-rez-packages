"""Build a deterministic, directly extractable Rez repository from a pinned payload."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import platform as host_platform
import posixpath
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import jsonschema
import py7zr
import zstandard
from py7zr.exceptions import AbsolutePathError, ArchiveError, PasswordRequired

ROOT = Path(__file__).resolve().parents[1]
DEFINITION_SCHEMA = ROOT / "schema" / "bundle-definition.schema.json"
MANIFEST_SCHEMA = ROOT / "schema" / "bundle-manifest.schema.json"
MINIMUM_NATIVE_7ZIP_VERSION = (26, 4)


class BundleError(RuntimeError):
    """A bundle cannot be built without violating its published contract."""


def load_definition(path: Path) -> dict:
    """Load and validate the portable recipe (metadata paths are relative to this file)."""
    definition = json.loads(path.read_text(encoding="utf-8"))
    validate_definition(definition)
    return definition


def validate_definition(definition: dict) -> None:
    _build_revision(definition)
    _validate_json(definition, DEFINITION_SCHEMA)
    targets = definition["targets"] + definition["unsupported_targets"]
    triples = [target["triple"] for target in targets]
    if len(triples) != len(set(triples)):
        raise BundleError("bundle definition contains duplicate target triples")
    _safe_relative(definition["package"]["definition"]["source"])
    for relative in definition["package"]["path_entries"]:
        _safe_relative(relative)
    for metadata in definition["metadata"]:
        _safe_relative(metadata["source"])
        _safe_relative(metadata["destination"])
    for target in definition["targets"]:
        if target["payload"]["format"] == "binary" and len(target["payload"]["mappings"]) != 1:
            raise BundleError("a binary payload must have exactly one mapping")
        for mapping in target["payload"]["mappings"]:
            _safe_relative(mapping["source"], allow_root=True)
            _safe_relative(mapping["destination"], allow_root=True)


def _build_revision(definition: dict) -> int:
    if "build_revision" not in definition:
        return 0
    revision = definition["build_revision"]
    if type(revision) is not int or revision <= 0:
        raise BundleError("build_revision must be a positive integer when supplied")
    return revision


def expected_release_tag(definition: dict) -> str:
    """Identify immutable packaging revisions without changing the runtime version."""
    base = f"{definition['tool']}-{definition['version']}"
    revision = _build_revision(definition)
    return f"{base}-r{revision}" if revision else base


def build_bundle(
    definition: dict,
    triple: str,
    output_directory: Path,
    *,
    source_archive: Path | None = None,
    metadata_directory: Path | None = None,
    sdk_executable: Path | None = None,
    repositories: Iterable[Path] = (),
    smoke_test: bool = True,
) -> Path:
    """Build one target and its SHA-256 companion; never execute a foreign payload."""
    validate_definition(definition)
    target = _select_target(definition, triple)
    package_source = _read_package_definition(definition, metadata_directory)
    tool, version = definition["tool"], definition["version"]
    asset_name = f"{tool}-{version}-{triple}.rez.tar.zst"
    output_directory.mkdir(parents=True, exist_ok=True)
    output_path = output_directory / asset_name
    with tempfile.TemporaryDirectory(prefix="vx-rez-bundle-") as temporary:
        work = Path(temporary).resolve()
        pinned_definition = work / "package.py"
        pinned_definition.write_bytes(package_source)
        plan = _installation_plan(
            pinned_definition, definition, target, sdk_executable, repositories
        )
        repository = work / "repository"
        repository.mkdir()
        package_root = _planned_directory(repository, plan["package_relative_path"])
        package_root.mkdir(parents=True)
        package_root.joinpath("package.py").write_bytes(package_source)
        variant_root = _planned_directory(repository, plan["variant_relative_path"])
        payload_root = _planned_directory(repository, plan["variant_relative_path"] + "/payload")
        payload_root.mkdir(parents=True)
        source = source_archive
        if source is None:
            source = work / "upstream-payload"
            _download(target["upstream"]["url"], source)
        source = source.resolve()
        _verify_sha256(source, target["upstream"]["sha256"], "upstream payload")
        executables = _install_payload(source, work / "source", payload_root, target["payload"])
        _install_metadata(definition, metadata_directory, package_root, payload_root)
        _audit_links(payload_root)
        _materialize_links(payload_root, executables)
        _write_system_package(repository, "platform", target["platform"])
        _write_system_package(repository, "arch", target["arch"])
        manifest = _bundle_manifest(definition, target, asset_name, plan)
        _validate_json(manifest, MANIFEST_SCHEMA)
        _write_json(package_root / "manifest.json", manifest)
        _write_json(
            package_root / "provenance.json",
            {
                "upstream": definition["provenance"],
                "payload": target["upstream"],
                "metadata": definition["metadata"],
                "package_definition": definition["package"]["definition"],
                "installation_plan": plan,
                "build_revision": _build_revision(definition),
                "release_tag": expected_release_tag(definition),
                "recipe_sha256": hashlib.sha256(
                    json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
            },
        )
        _check_payload_collisions(repository)
        _write_repository_checksums(repository, package_root / "sha256sums.txt")
        if smoke_test:
            _assert_native_target(target)
            smoke_root = work / "smoke" / tool / version
            shutil.copytree(package_root, smoke_root)
            smoke_variant = smoke_root / variant_root.relative_to(package_root)
            _smoke_test(smoke_variant, definition, target)
        _write_reproducible_tar_zstd(
            repository,
            output_path,
            definition["release_date"],
            executable_paths={
                f"{plan['variant_relative_path']}/payload/{path}" for path in executables
            },
        )
    output_path.with_name(f"{asset_name}.sha256").write_text(
        f"{_sha256(output_path)}  {asset_name}\n", encoding="utf-8", newline="\n"
    )
    return output_path


def _installation_plan(
    package: Path,
    definition: dict,
    target: dict,
    sdk_executable: Path | None,
    repositories: Iterable[Path],
) -> dict:
    """Ask the explicit SDK for Core's layout; never infer variant semantics here."""
    if sdk_executable is None:
        configured = os.environ.get("VX_REZ_SDK_EXECUTABLE")
        sdk_executable = Path(configured) if configured else None
    if sdk_executable is None:
        raise BundleError("--sdk-executable or VX_REZ_SDK_EXECUTABLE is required")
    try:
        executable = sdk_executable.resolve(strict=True)
        if not executable.is_file():
            raise BundleError("SDK executable must be a regular file")
        command = [
            str(executable),
            "installation-plan",
            "--definition",
            str(package),
            "--platform",
            target["platform"],
            "--arch",
            target["arch"],
            "--json",
        ]
        for repository in repositories:
            dependency = repository.resolve(strict=True)
            if not dependency.is_dir():
                raise BundleError("SDK dependency repository must be a directory")
            command.extend(["--repository", str(dependency)])
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=60,
            cwd=package.parent,
            stdin=subprocess.DEVNULL,
            shell=False,
        )
    except (OSError, UnicodeError, subprocess.SubprocessError) as error:
        raise BundleError(f"SDK installation planning failed: {error}") from error

    def unique_keys(pairs: list[tuple[str, object]]) -> dict:
        document = {}
        for key, value in pairs:
            if key in document:
                raise BundleError(f"duplicate SDK installation plan key: {key}")
            document[key] = value
        return document

    try:
        if len(result.stdout) > 1024 * 1024:
            raise BundleError("SDK installation plan is too large")
        plan = json.loads(result.stdout, object_pairs_hook=unique_keys)
    except (TypeError, ValueError) as error:
        raise BundleError("SDK installation plan must be valid JSON") from error
    fields = {
        "schema_version",
        "name",
        "version",
        "platform",
        "arch",
        "variant_index",
        "variant_requirements",
        "package_relative_path",
        "variant_relative_path",
    }
    if not isinstance(plan, dict) or set(plan) != fields:
        raise BundleError("SDK installation plan has unexpected fields")
    if type(plan["schema_version"]) is not int or plan["schema_version"] != 1:
        raise BundleError("unsupported SDK installation plan schema")
    for key, expected in (
        ("name", definition["tool"]),
        ("version", definition["version"]),
        ("platform", target["platform"]),
        ("arch", target["arch"]),
    ):
        if plan[key] != expected:
            raise BundleError(f"SDK installation plan does not match requested {key}")
    index, requirements = plan["variant_index"], plan["variant_requirements"]
    if (index is not None and (type(index) is not int or index < 0)) or not (
        isinstance(requirements, list)
        and all(isinstance(requirement, str) and requirement for requirement in requirements)
    ):
        raise BundleError("SDK installation plan has invalid variant metadata")
    expected_package = f"{definition['tool']}/{definition['version']}"
    package_path, variant_path = plan["package_relative_path"], plan["variant_relative_path"]
    for path in (package_path, variant_path):
        if not isinstance(path, str) or _safe_relative(path) != path:
            raise BundleError("SDK installation plan paths must be canonical relative paths")
    if package_path != expected_package or not (
        variant_path == package_path or variant_path.startswith(package_path + "/")
    ):
        raise BundleError("SDK installation plan leaves the requested package root")
    if index is None and (requirements or variant_path != package_path):
        raise BundleError("SDK installation plan has inconsistent unvarianted layout")
    suffix = PurePosixPath(variant_path).relative_to(PurePosixPath(package_path))
    if suffix.parts and suffix.parts[0].casefold() in {
        "package.py",
        "manifest.json",
        "provenance.json",
        "sha256sums.txt",
    }:
        raise BundleError("SDK installation path collides with package metadata")
    return plan


def _planned_directory(repository: Path, relative: str) -> Path:
    """Reject links and non-directories at every existing layout component."""
    path = repository
    for component in PurePosixPath(_safe_relative(relative)).parts:
        path /= component
        if path.exists() or path.is_symlink():
            information = path.lstat()
            if not stat.S_ISDIR(information.st_mode) or (
                getattr(information, "st_file_attributes", 0) & (0x0400 | 0x0040)
            ):
                raise BundleError("SDK installation path contains a link or non-directory")
        if not path.resolve().is_relative_to(repository.resolve()):
            raise BundleError("SDK installation path escapes the repository")
    return path


def _select_target(definition: dict, triple: str) -> dict:
    for target in definition["targets"]:
        if target["triple"] == triple:
            return target
    for target in definition["unsupported_targets"]:
        if target["triple"] == triple:
            raise BundleError(f"target {triple!r} is unsupported: {target['reason']}")
    raise BundleError(f"target {triple!r} is not declared by the bundle definition")


def _validate_json(document: dict, schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda error: str(list(error.path)))
    if errors:
        raise BundleError(
            f"{schema_path.name} validation failed: " + "; ".join(error.message for error in errors)
        )


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "vx-rez-packages/1"})
    try:
        with (
            urllib.request.urlopen(request, timeout=60) as response,
            destination.open("wb") as output,
        ):
            if urllib.parse.urlsplit(response.url).scheme != "https":
                raise BundleError("upstream payload redirected to a non-HTTPS URL")
            shutil.copyfileobj(response, output, length=1024 * 1024)
    except OSError as error:
        raise BundleError(f"failed to download {url}: {error}") from error


def _verify_sha256(path: Path, expected: str, label: str) -> None:
    actual = _sha256(path)
    if actual != expected:
        raise BundleError(f"{label} checksum mismatch: expected {expected}, got {actual}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(name: str, *, allow_root: bool = False) -> str:
    if name == "." and allow_root:
        return name
    parts = name.rstrip("/").split("/")
    if (
        not name
        or name.startswith("/")
        or "\\" in name
        or ":" in name
        or "\x00" in name
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise BundleError(f"unsafe relative path: {name!r}")
    for part in parts:
        reserved = part.split(".")[0].rstrip(" ").upper()
        if (
            part.endswith((".", " "))
            or any(ord(character) < 32 or character in '<>"|?*' for character in part)
            or reserved in {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
            or reserved in {f"COM{number}" for number in "123456789¹²³"}
            or reserved in {f"LPT{number}" for number in "123456789¹²³"}
        ):
            raise BundleError(f"non-portable relative path: {name!r}")
    return "/".join(parts)


def _collision_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def _validate_archive_entries(entries: list[tuple[str, str, str | None]]) -> None:
    """Validate the entire member graph before creating any filesystem entries."""
    seen: dict[str, str] = {}
    kinds: dict[str, str] = {}
    links: dict[str, str] = {}
    aliases: dict[str, str] = {}
    for name, kind, link in entries:
        key = _collision_key(_safe_relative(name))
        for prefix in [PurePosixPath(name), *PurePosixPath(name).parents]:
            spelling = str(prefix)
            if spelling == ".":
                continue
            alias = _collision_key(spelling)
            if alias in aliases and aliases[alias] != spelling:
                raise BundleError(f"archive member collision: {spelling!r} and {aliases[alias]!r}")
            aliases[alias] = spelling
        if key in seen:
            raise BundleError(f"archive member collision: {name!r} and {seen[key]!r}")
        seen[key], kinds[key] = name, kind
        if link is not None:
            if not link or link.startswith("/") or "\\" in link or ":" in link or "\x00" in link:
                raise BundleError(f"unsafe archive link: {name!r} -> {link!r}")
            target = posixpath.normpath(
                posixpath.join(posixpath.dirname(name), link) if kind == "symlink" else link
            )
            links[key] = _collision_key(_safe_relative(target))
    for key in kinds:
        for parent in PurePosixPath(key).parents:
            if str(parent) != "." and kinds.get(str(parent), "dir") != "dir":
                raise BundleError(f"archive member has a non-directory parent: {seen[key]!r}")
    for key, target in links.items():
        visited = {key}
        while target in links:
            if target in visited:
                raise BundleError(f"archive link cycle: {seen[key]!r}")
            visited.add(target)
            target = links[target]
        if target not in kinds and not any(item.startswith(target + "/") for item in kinds):
            raise BundleError(f"archive link target is missing: {seen[key]!r}")
        if kinds[key] == "hardlink" and kinds.get(target) != "file":
            raise BundleError(f"archive hardlink must name a regular file: {seen[key]!r}")


def _seven_zip_entries(archive: py7zr.SevenZipFile) -> tuple[list[tuple[str, str, None]], set[str]]:
    """Inspect raw 7z attributes; public list() omits reparse/device bits and Unix modes.

    py7zr 1.1.x exposes parsed member metadata before extracting payload streams.
    Only unambiguous regular files and directories are admitted. Windows reparse
    points cover junction/link encodings even on a non-Windows build host.
    """
    entries = []
    executables = set()
    for member in archive.files:
        properties = member.file_properties()
        attributes = properties.get("attributes")
        if type(attributes) is not int or not 0 <= attributes <= 0xFFFFFFFF:
            raise BundleError(f"7z member lacks explicit type attributes: {member.filename!r}")
        # These constants are format bits, independent of the extraction host OS.
        if attributes & (0x0400 | 0x0040):
            raise BundleError(f"unsupported 7z reparse point or device: {member.filename!r}")
        if properties.get("startpos") is not None or any(
            properties.get(key)
            for key in ("is_hardlink", "hardlink", "linkname", "linkpath", "reparse")
        ):
            raise BundleError(f"unsupported 7z link or special metadata: {member.filename!r}")
        is_directory = bool(attributes & 0x0010)
        unix_mode = attributes >> 16 if attributes & 0x8000 else None
        if unix_mode is not None and stat.S_IFMT(unix_mode) != (
            stat.S_IFDIR if is_directory else stat.S_IFREG
        ):
            raise BundleError(f"unsupported or ambiguous 7z Unix member type: {member.filename!r}")
        if (
            member.is_symlink
            or member.is_junction
            or member.is_socket
            or member.is_directory != is_directory
            or member.is_file != (not is_directory)
        ):
            raise BundleError(f"unsupported or ambiguous 7z member type: {member.filename!r}")
        name = member.filename.rstrip("/") if is_directory else member.filename
        entries.append((name, "dir" if is_directory else "file", None))
        if not is_directory and unix_mode is not None and unix_mode & 0o111:
            executables.add(name)
    _validate_archive_entries(entries)
    return entries, executables


def _run_native_7zip(
    arguments: list[str], destination: Path, timeout: int
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["vx", "7zip", *arguments],
            cwd=destination,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            check=True,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "").strip()[:2000]
        raise BundleError(
            f"native 7-Zip failed with exit code {error.returncode}: {detail}"
        ) from error
    except subprocess.TimeoutExpired as error:
        raise BundleError(f"native 7-Zip exceeded its {timeout}-second timeout") from error


def _extract_native_7zip(source: Path, destination: Path) -> None:
    information = _run_native_7zip(["i"], destination, 60)
    version = re.search(
        r"(?m)^7-Zip(?: \([^\r\n)]*\))? (\d+)\.(\d+)(?=\s|$)",
        information.stdout,
    )
    if version is None or tuple(map(int, version.groups())) < MINIMUM_NATIVE_7ZIP_VERSION:
        raise BundleError("native-7zip requires official 7-Zip 26.04 or newer via vx 7zip")
    _run_native_7zip(
        [
            "x",
            "-t7z",
            "-y",
            "-aoa",
            "-bd",
            "-sns-",
            "-snh-",
            "-snl-",
            "-spd",
            "-spod",
            f"-o{destination.resolve()}",
            "--",
            str(source.resolve()),
        ],
        destination,
        600,
    )


def _audit_native_tree(destination: Path, entries: list[tuple[str, str, None]]) -> None:
    """Require exactly the preflighted files and directories without following links."""
    expected = {name: kind for name, kind, _ in entries}
    for name in list(expected):
        for parent in PurePosixPath(name).parents:
            if str(parent) != ".":
                expected.setdefault(str(parent), "dir")
    root_information = destination.lstat()
    if not stat.S_ISDIR(root_information.st_mode) or (
        getattr(root_information, "st_file_attributes", 0) & (0x0400 | 0x0040)
    ):
        raise BundleError("native 7-Zip replaced its extraction directory with a special entry")
    root = destination.resolve()
    pending = [destination]
    found = set()
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as children:
            for child in children:
                path = Path(child.path)
                relative = _safe_relative(path.relative_to(destination).as_posix())
                # Windows directory metadata can omit link counts; query the actual path.
                information = path.lstat()
                mode = information.st_mode
                if (
                    getattr(information, "st_file_attributes", 0) & (0x0400 | 0x0040)
                    or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode))
                    or (stat.S_ISREG(mode) and information.st_nlink != 1)
                ):
                    raise BundleError(f"native 7-Zip emitted a link or special entry: {relative!r}")
                if not path.resolve().is_relative_to(root):
                    raise BundleError(f"native 7-Zip emitted an escaping path: {relative!r}")
                kind = "dir" if stat.S_ISDIR(mode) else "file"
                if expected.get(relative) != kind:
                    raise BundleError(f"native 7-Zip emitted an unexpected entry: {relative!r}")
                found.add(relative)
                if kind == "dir":
                    pending.append(path)
    missing = set(expected) - found
    if missing:
        raise BundleError(f"native 7-Zip omitted archive entries: {sorted(missing)[:10]!r}")


@contextmanager
def _open_tar_archive(source: Path, archive_format: str) -> Iterator[tarfile.TarFile]:
    if archive_format == "tar.zst":
        with (
            source.open("rb") as compressed,
            zstandard.ZstdDecompressor().stream_reader(compressed) as reader,
            tempfile.TemporaryFile() as decoded,
        ):
            shutil.copyfileobj(reader, decoded, length=1024 * 1024)
            decoded.seek(0)
            with tarfile.open(fileobj=decoded, mode="r:") as archive:
                yield archive
    else:
        with tarfile.open(source, "r:*") as archive:
            yield archive


def _extract_archive(
    source: Path, destination: Path, archive_format: str, *, decoder: str = "py7zr"
) -> set[str]:
    if decoder not in {"py7zr", "native-7zip"} or (decoder != "py7zr" and archive_format != "7z"):
        raise BundleError("native-7zip is only an explicit decoder for 7z payloads")
    destination.mkdir()
    executables = set()
    try:
        if archive_format == "zip":
            with zipfile.ZipFile(source) as archive:
                members = archive.infolist()
                entries = []
                for member in members:
                    mode = member.external_attr >> 16
                    kind = "dir" if member.is_dir() else "file"
                    link = None
                    if stat.S_ISLNK(mode):
                        kind, link = "symlink", archive.read(member).decode("utf-8")
                    elif stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}:
                        raise BundleError(f"unsupported zip member: {member.filename!r}")
                    entries.append((member.filename.rstrip("/"), kind, link))
                    if kind == "file" and mode & 0o111:
                        executables.add(member.filename.rstrip("/"))
                _validate_archive_entries(entries)
                for member, (name, kind, link) in zip(members, entries, strict=True):
                    path = destination / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if kind == "dir":
                        path.mkdir(exist_ok=True)
                    elif kind == "symlink":
                        path.symlink_to(link)
                    else:
                        with archive.open(member) as input_file, path.open("wb") as output:
                            shutil.copyfileobj(input_file, output)
                        path.chmod(0o755 if (member.external_attr >> 16) & 0o111 else 0o644)
        elif archive_format == "7z":
            with py7zr.SevenZipFile(source, mode="r") as archive:
                if archive.needs_password():
                    raise BundleError("encrypted 7z payloads are unsupported")
                entries, executables = _seven_zip_entries(archive)
                if decoder == "py7zr":
                    unsupported = [
                        method.rstrip("*")
                        for method in archive.archiveinfo().method_names
                        if method.endswith("*")
                    ]
                    if unsupported:
                        raise BundleError(
                            f"py7zr does not support 7z methods {unsupported!r}; "
                            "explicitly set payload.decoder to 'native-7zip'"
                        )
                    archive.extractall(path=destination)
            if decoder == "native-7zip":
                _extract_native_7zip(source, destination)
                _audit_native_tree(destination, entries)
        else:
            with _open_tar_archive(source, archive_format) as archive:
                members = archive.getmembers()
                entries = []
                for member in members:
                    if member.isdir():
                        kind = "dir"
                    elif member.isfile():
                        kind = "file"
                    elif member.issym():
                        kind = "symlink"
                    elif member.islnk():
                        kind = "hardlink"
                    else:
                        raise BundleError(f"unsupported tar member: {member.name!r}")
                    entries.append(
                        (
                            member.name.rstrip("/"),
                            kind,
                            member.linkname if member.issym() or member.islnk() else None,
                        )
                    )
                    if member.isfile() and member.mode & 0o111:
                        executables.add(member.name.rstrip("/"))
                _validate_archive_entries(entries)
                for member in members:
                    if member.islnk() and (member.mode & 0o111 or member.linkname in executables):
                        executables.add(member.name.rstrip("/"))
                archive.extractall(destination, members=members, filter="data")
        _audit_links(destination)
        return executables
    except (
        tarfile.TarError,
        zipfile.BadZipFile,
        zstandard.ZstdError,
        ArchiveError,
        AbsolutePathError,
        PasswordRequired,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise BundleError(f"failed to safely extract {source}: {error}") from error


def _install_payload(source: Path, extracted: Path, payload: Path, specification: dict) -> set[str]:
    executables = set()
    if specification["format"] == "binary":
        mapping = specification["mappings"][0]
        if mapping["source"] != ".":
            raise BundleError("binary payload mapping source must be '.'")
        destination = payload / mapping["destination"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        destination.chmod(0o755 if mapping.get("executable", False) else 0o644)
        return {mapping["destination"]} if mapping.get("executable", False) else set()
    source_executables = _extract_archive(
        source,
        extracted,
        specification["format"],
        decoder=specification.get("decoder", "py7zr"),
    )

    def copy_with_mode(entry: Path, destination: Path) -> None:
        _copy_entry(entry, destination)
        if (
            entry.is_file()
            and entry.resolve().relative_to(extracted).as_posix() in source_executables
        ):
            executables.add(destination.relative_to(payload).as_posix())

    for mapping in specification["mappings"]:
        entry = extracted / mapping["source"]
        destination = payload / mapping["destination"]
        if not entry.exists():
            raise BundleError(f"payload mapping source is missing: {mapping['source']!r}")
        if entry.is_dir():
            for child in sorted(entry.rglob("*")):
                relative = child.relative_to(entry)
                copy_with_mode(child, destination / relative)
        else:
            copy_with_mode(entry, destination)
        if mapping.get("executable", False):
            if not destination.is_file():
                raise BundleError("executable mapping must name one regular file")
            destination.chmod(0o755)
            executables.add(destination.relative_to(payload).as_posix())
    _check_payload_collisions(payload)
    return executables


def _copy_entry(source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        if source.is_dir() and not source.is_symlink() and destination.is_dir():
            return
        raise BundleError(f"payload mapping collision at {destination.name!r}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_symlink():
        destination.symlink_to(source.readlink(), target_is_directory=source.is_dir())
    elif source.is_dir():
        destination.mkdir()
    else:
        shutil.copyfile(source, destination)
        destination.chmod(0o755 if source.stat().st_mode & 0o111 else 0o644)


def _check_payload_collisions(root: Path) -> None:
    seen = set()
    for path in root.rglob("*"):
        key = _collision_key(path.relative_to(root).as_posix())
        if key in seen:
            raise BundleError(f"payload contains a portable-path collision: {key!r}")
        seen.add(key)


def _audit_links(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            try:
                path.resolve(strict=True).relative_to(root.resolve())
            except (OSError, RuntimeError, ValueError) as error:
                raise BundleError(
                    f"link escapes its root or has no target: {path.name!r}"
                ) from error


def _materialize_links(root: Path, executable_paths: set[str] | None = None) -> None:
    """Preserve internal aliases as regular content for portable, fully hashed repositories."""
    links = [path for path in root.rglob("*") if path.is_symlink()]
    executables = executable_paths if executable_paths is not None else set()

    def copy_resolved(
        source: Path, destination: Path, ancestors: frozenset[Path], logical_path: Path
    ) -> None:
        resolved = source.resolve(strict=True)
        try:
            resolved.relative_to(root.resolve())
        except ValueError as error:
            raise BundleError("payload link escapes its root") from error
        if resolved.is_dir():
            if resolved in ancestors:
                raise BundleError(f"payload directory link cycle: {source.name!r}")
            destination.mkdir()
            for child in sorted(resolved.iterdir()):
                copy_resolved(
                    child,
                    destination / child.name,
                    ancestors | {resolved},
                    logical_path / child.name,
                )
        else:
            shutil.copyfile(resolved, destination)
            is_executable = resolved.relative_to(root).as_posix() in executables
            destination.chmod(0o755 if is_executable else 0o644)
            if is_executable:
                executables.add(logical_path.as_posix())

    for index, link in enumerate(links):
        staging = root.parent / f"materialized-link-{index}"
        copy_resolved(link, staging, frozenset(link.parents), link.relative_to(root))
        link.unlink()
        staging.replace(link)


def _install_metadata(
    definition: dict, directory: Path | None, package_root: Path, payload_root: Path
) -> None:
    if directory is None:
        raise BundleError("metadata_directory is required for pinned license and notices")
    for metadata in definition["metadata"]:
        source = directory / metadata["source"]
        try:
            source.resolve(strict=True).relative_to(directory.resolve())
        except (OSError, ValueError) as error:
            raise BundleError("metadata source must remain inside the recipe directory") from error
        _verify_sha256(source, metadata["sha256"], "metadata")
        destination = package_root / metadata["destination"]
        if (
            destination.exists()
            or destination.name.casefold()
            in {"package.py", "manifest.json", "provenance.json", "sha256sums.txt"}
            or destination.parts[len(package_root.parts)].casefold() == "payload"
            or destination.is_relative_to(payload_root)
        ):
            raise BundleError(f"metadata destination collision: {metadata['destination']!r}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        destination.chmod(0o644)


def _module_identity_bindings(node: ast.AST) -> Iterable[tuple[str, ast.AST]]:
    """Find identity bindings in module scope, including outer scope expressions."""
    name = None
    if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
        name = node.id
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        name = node.name
    elif isinstance(node, ast.alias):
        if node.name == "*":
            raise BundleError("package definition cannot use module wildcard imports")
        name = node.asname or node.name.split(".")[0]
    elif isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)):
        name = node.name
    elif isinstance(node, ast.MatchMapping):
        name = node.rest
    if name in {"name", "version"}:
        yield name, node
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        children = [node.args, *node.decorator_list]
        if node.returns is not None:
            children.append(node.returns)
    elif isinstance(node, ast.ClassDef):
        children = [*node.bases, *node.keywords, *node.decorator_list]
    elif isinstance(node, ast.Lambda):
        children = [node.args]
    elif isinstance(node, ast.comprehension):
        children = [node.iter, *node.ifs]
    else:
        children = ast.iter_child_nodes(node)
    for child in children:
        yield from _module_identity_bindings(child)


def _read_package_definition(definition: dict, directory: Path | None) -> bytes:
    """Validate pinned declarations without executing the actual Rez definition."""
    if directory is None:
        raise BundleError("metadata_directory is required for the pinned package definition")
    specification = definition["package"]["definition"]
    source = directory / specification["source"]
    try:
        source.resolve(strict=True).relative_to(directory.resolve())
        if source.is_symlink() or not source.is_file():
            raise BundleError("package definition source must be a regular file")
        contents = source.read_bytes()
    except (OSError, ValueError) as error:
        raise BundleError(
            "package definition source must remain inside the recipe directory"
        ) from error
    actual = hashlib.sha256(contents).hexdigest()
    if actual != specification["sha256"]:
        raise BundleError(
            "package definition checksum mismatch: "
            f"expected {specification['sha256']}, got {actual}"
        )
    try:
        module = ast.parse(contents, filename=specification["source"])
    except (SyntaxError, ValueError) as error:
        raise BundleError(f"package definition contains invalid Python syntax: {error}") from error
    expected = {"name": definition["tool"], "version": definition["version"]}
    declarations = {}
    for statement in module.body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target, value = statement.targets[0], statement.value
        elif isinstance(statement, ast.AnnAssign):
            target, value = statement.target, statement.value
        else:
            continue
        if isinstance(target, ast.Name) and target.id in expected:
            if (
                target.id in declarations
                or not isinstance(value, ast.Constant)
                or type(value.value) is not str
                or value.value != expected[target.id]
            ):
                raise BundleError(
                    f"package definition {target.id} must be one matching literal string"
                )
            declarations[target.id] = target
    if set(declarations) != set(expected):
        raise BundleError(
            "package definition requires direct literal name and version declarations"
        )
    for name, node in _module_identity_bindings(module):
        if node is not declarations[name]:
            raise BundleError(f"package definition has another module binding for {name}")
    if any(
        isinstance(node, ast.Global) and set(node.names) & set(expected)
        for node in ast.walk(module)
    ):
        raise BundleError("package definition cannot globally rebind name or version")
    return contents


def _write_system_package(repository: Path, family: str, version: str) -> None:
    root = repository / family / version
    root.mkdir(parents=True, exist_ok=True)
    root.joinpath("package.py").write_text(
        f"name = {family!r}\nversion = {version!r}\n", encoding="utf-8", newline="\n"
    )


def _bundle_manifest(definition: dict, target: dict, asset_name: str, plan: dict) -> dict:
    package_root = plan["package_relative_path"]
    return {
        "schema_version": 1,
        "tool": definition["tool"],
        "version": definition["version"],
        "platform": target["platform"],
        "arch": target["arch"],
        "triple": target["triple"],
        "asset_name": asset_name,
        "package_root": package_root,
        "payload_root": f"{plan['variant_relative_path']}/payload",
        "upstream": {
            "manifest_url": definition["upstream_manifest"],
            "archive_url": target["upstream"]["url"],
            "archive_sha256": target["upstream"]["sha256"],
        },
        "checksums": {
            "algorithm": "sha256",
            "file": f"{package_root}/sha256sums.txt",
            "scope": "all regular repository files except sha256sums.txt",
        },
        "compatibility": definition["compatibility"],
    }


def _write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


def _regular_files(root: Path) -> Iterable[Path]:
    return sorted(
        (path for path in root.rglob("*") if path.is_file() and not path.is_symlink()),
        key=lambda path: path.as_posix(),
    )


def _write_repository_checksums(repository: Path, destination: Path) -> None:
    lines = [
        f"{_sha256(path)}  {path.relative_to(repository).as_posix()}"
        for path in _regular_files(repository)
        if path != destination
    ]
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _normalize_machine(machine: str) -> str:
    normalized = machine.lower()
    if normalized in {"amd64", "x64", "x86_64"}:
        return "x86_64"
    if normalized in {"arm64", "aarch64"}:
        return "arm_64"
    return normalized


def _assert_native_target(target: dict) -> None:
    native_platform = {"Darwin": "osx", "Windows": "windows", "Linux": "linux"}.get(
        host_platform.system(), host_platform.system().lower()
    )
    native_arch = _normalize_machine(host_platform.machine())
    if (native_platform, native_arch) != (target["platform"], target["arch"]):
        raise BundleError(
            "smoke tests require the declared native target: "
            f"wanted {target['platform']}/{target['arch']}, "
            f"got {native_platform}/{native_arch}"
        )


def _smoke_test(package_root: Path, definition: dict, target: dict) -> None:
    substitutions = {
        "root": str(package_root),
        "version": definition["version"],
        "exe": ".exe" if target["platform"] == "windows" else "",
    }
    smoke = target.get("smoke_test", definition["package"]["smoke_test"])
    command = [argument.format_map(substitutions) for argument in smoke["command"]]
    executable = Path(command[0])
    try:
        executable.resolve(strict=True).relative_to(package_root.resolve())
    except (OSError, ValueError) as error:
        raise BundleError("smoke command must execute a file inside this package") from error
    try:
        with tempfile.TemporaryDirectory(prefix="vx-rez-smoke-home-") as temporary:
            home = Path(temporary)
            environment = os.environ.copy()
            for variable in ("PYTHONHOME", "PYTHONPATH"):
                environment.pop(variable, None)
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            for variable in ("HOME", "USERPROFILE"):
                environment[variable] = str(home)
            for variable, child in {
                "XDG_CONFIG_HOME": "config",
                "XDG_CACHE_HOME": "cache",
                "XDG_DATA_HOME": "data",
                "XDG_STATE_HOME": "state",
                "APPDATA": "roaming",
                "LOCALAPPDATA": "local",
                "TMPDIR": "temp",
                "TMP": "temp",
                "TEMP": "temp",
            }.items():
                directory = home / child
                directory.mkdir(exist_ok=True)
                environment[variable] = str(directory)
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=smoke.get("timeout_seconds", 60),
                cwd=package_root,
                env=environment,
            )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise BundleError(f"native smoke test failed: {error}") from error
    expected = smoke["expect"].format_map(substitutions)
    if expected not in result.stdout + result.stderr:
        raise BundleError(f"unexpected smoke output: {result.stdout!r} {result.stderr!r}")


def _write_reproducible_tar_zstd(
    repository: Path, output: Path, release_date: str, *, executable_paths: set[str]
) -> None:
    epoch = int(datetime.fromisoformat(release_date).replace(tzinfo=UTC).timestamp())

    def normalize(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        info.mtime = epoch
        info.mode = 0o755 if info.isdir() or info.name in executable_paths else 0o644
        if info.issym():
            info.mode = 0o777
        return info

    with output.open("wb") as destination:
        compressor = zstandard.ZstdCompressor(level=10, threads=0)
        with (
            compressor.stream_writer(destination, closefd=False) as compressed,
            tarfile.open(fileobj=compressed, mode="w|", format=tarfile.PAX_FORMAT) as archive,
        ):
            for path in sorted(repository.rglob("*"), key=lambda entry: entry.as_posix()):
                archive.add(
                    path,
                    arcname=path.relative_to(repository).as_posix(),
                    recursive=False,
                    filter=normalize,
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", type=Path, required=True)
    parser.add_argument("--triple", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-archive", type=Path)
    parser.add_argument("--metadata-dir", type=Path)
    parser.add_argument("--sdk-executable", type=Path)
    parser.add_argument("--repository", type=Path, action="append", default=[])
    parser.add_argument("--no-smoke-test", action="store_true")
    args = parser.parse_args()
    try:
        output = build_bundle(
            load_definition(args.definition),
            args.triple,
            args.output_dir,
            source_archive=args.source_archive,
            metadata_directory=args.metadata_dir or args.definition.parent,
            sdk_executable=args.sdk_executable,
            repositories=args.repository,
            smoke_test=not args.no_smoke_test,
        )
    except (BundleError, OSError, ValueError, KeyError) as error:
        raise SystemExit(str(error)) from error
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
