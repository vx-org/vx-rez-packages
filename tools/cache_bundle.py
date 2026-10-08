"""Verify and cache a released Rez repository for SDK acceptance.

This utility owns no solver or environment semantics. It returns a verified
repository directory to an SDK consumer. Both the index and bundle are pinned.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

import jsonschema
import zstandard


class CacheError(ValueError):
    """A release, checksum, platform selection, or cache contract failed."""


def _digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _checked_download(url: str, sha256: str, path: Path, *, offline: bool) -> Path:
    if not re.fullmatch(r"[a-f0-9]{64}", sha256):
        raise CacheError("a lowercase SHA-256 pin is required")
    if urlparse(url).scheme != "https":
        raise CacheError("release URLs must use HTTPS")
    if path.exists():
        if _digest(path) != sha256:
            raise CacheError(f"cached checksum mismatch: {path.name}")
        return path
    if offline:
        raise CacheError(f"offline cache miss: {path.name}; provision this pin while online")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as destination:
            temporary = Path(destination.name)
            with urlopen(url, timeout=30) as source:
                shutil.copyfileobj(source, destination)
        if _digest(temporary) != sha256:
            raise CacheError(f"download checksum mismatch: {path.name}")
        os.replace(temporary, path)
    except (OSError, URLError) as error:
        raise CacheError(f"download failed for {url}: {error}") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


def _relative(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {".", ".."} or ":" in part or "\\" in part for part in path.parts)
    ):
        raise CacheError(f"unsafe repository member: {name}")
    return path


def _verify_repository(repository: Path, selected: dict) -> None:
    package_root = repository.joinpath(*_relative(selected["package_root"]).parts)
    manifest_path = package_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema = json.loads(
        (Path(__file__).parents[1] / "schema/bundle-manifest.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.validate(manifest, schema)
    for key in ("tool", "version", "platform", "arch", "triple", "asset_name", "package_root"):
        if manifest[key] != selected[key]:
            raise CacheError(f"bundle manifest does not match release index: {key}")
    checksum_path = repository.joinpath(*_relative(manifest["checksums"]["file"]).parts)
    declared: set[str] = set()
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([a-f0-9]{64})  (.+)", line)
        if match is None:
            raise CacheError("malformed repository checksum list")
        expected, name = match.groups()
        relative = _relative(name).as_posix()
        if relative in declared:
            raise CacheError(f"duplicate repository checksum: {relative}")
        declared.add(relative)
        file = repository.joinpath(*_relative(relative).parts)
        if not file.is_file() or file.is_symlink() or _digest(file) != expected:
            raise CacheError(f"repository file checksum mismatch: {relative}")
    actual = {
        file.relative_to(repository).as_posix()
        for file in repository.rglob("*")
        if file.is_file() and file != checksum_path
    }
    if actual != declared or any(file.is_symlink() for file in repository.rglob("*")):
        raise CacheError("repository file set differs from checksum list")
    if not (package_root / "package.py").is_file():
        raise CacheError("bundle contains no Rez package definition")


def provision(
    index_url: str,
    index_sha256: str,
    cache: Path,
    *,
    tool: str,
    version: str,
    platform: str,
    arch: str,
    offline: bool = False,
) -> Path:
    """Select a pinned asset and return its fully verified local repository."""
    index_path = _checked_download(
        index_url, index_sha256, cache / "indexes" / index_sha256, offline=offline
    )
    index = json.loads(index_path.read_text(encoding="utf-8"))
    schema = json.loads(
        (Path(__file__).parents[1] / "schema/release-index.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(index, schema)
    matches = [
        bundle
        for bundle in index["bundles"]
        if (bundle["tool"], bundle["version"], bundle["platform"], bundle["arch"])
        == (tool, version, platform, arch)
    ]
    if len(matches) != 1:
        raise CacheError(
            f"expected exactly one bundle for {tool}@{version} {platform}/{arch}; "
            f"found {len(matches)}"
        )
    selected = matches[0]
    digest = selected["sha256"]
    archive_path = _checked_download(
        selected["download_url"], digest, cache / "archives" / digest, offline=offline
    )
    repository = cache / "repositories" / digest
    if repository.exists():
        _verify_repository(repository, selected)
        return repository
    repository.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=repository.parent) as temporary:
        staging = Path(temporary) / "repository"
        staging.mkdir()
        seen: set[str] = set()
        with (
            archive_path.open("rb") as source,
            zstandard.ZstdDecompressor().stream_reader(source) as decompressed,
            tarfile.open(fileobj=decompressed, mode="r|") as archive,
        ):
            for member in archive:
                relative = _relative(member.name).as_posix()
                if relative.casefold() in seen or not (member.isfile() or member.isdir()):
                    raise CacheError(f"duplicate or unsupported repository member: {member.name}")
                seen.add(relative.casefold())
                member.mode &= 0o777
                archive.extract(member, staging, filter="data")
        _verify_repository(staging, selected)
        try:
            staging.rename(repository)
        except FileExistsError:
            _verify_repository(repository, selected)
    return repository


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("index-url", "index-sha256", "tool", "version", "platform", "arch"):
        parser.add_argument(f"--{option}", required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    args = vars(parser.parse_args())
    try:
        print(provision(**args))
    except (
        CacheError,
        OSError,
        ValueError,
        jsonschema.ValidationError,
        tarfile.TarError,
        zstandard.ZstdError,
    ) as error:
        parser.exit(1, f"bundle verification failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
