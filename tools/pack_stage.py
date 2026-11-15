"""Deterministic archive and checksum steps shared by every bundle build path.

These rules are a published contract (schema-version 1), so both the original
``tools/build_bundle.py`` path and the ``rez build`` wrapper must produce byte
identical archives from identical repositories.
"""

from __future__ import annotations

import hashlib
import tarfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import zstandard

ZSTD_LEVEL = 10
EXECUTABLE_MODE = 0o755
REGULAR_MODE = 0o644


def regular_files(root: Path) -> Iterable[Path]:
    """List regular non-symlink files in a stable order."""
    return sorted(
        (path for path in root.rglob("*") if path.is_file() and not path.is_symlink()),
        key=lambda path: path.as_posix(),
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_repository_checksums(repository: Path, destination: Path) -> None:
    lines = [
        f"{sha256(path)}  {path.relative_to(repository).as_posix()}"
        for path in regular_files(repository)
        if path != destination
    ]
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def write_reproducible_tar_zstd(
    repository: Path, output: Path, release_date: str, *, executable_paths: set[str]
) -> None:
    """Write a reproducible zstd-compressed tar of a repository."""
    epoch = int(datetime.fromisoformat(release_date).replace(tzinfo=UTC).timestamp())

    def normalize(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        info.mtime = epoch
        info.mode = (
            EXECUTABLE_MODE if info.isdir() or info.name in executable_paths else REGULAR_MODE
        )
        if info.issym():
            info.mode = 0o777
        return info

    with output.open("wb") as destination:
        compressor = zstandard.ZstdCompressor(level=ZSTD_LEVEL, threads=0)
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
