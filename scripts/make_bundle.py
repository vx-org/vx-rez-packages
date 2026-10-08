#!/usr/bin/env python3
"""Package a Rez package tree into a bundle conforming to SPEC.md.

Usage
-----
    python scripts/make_bundle.py \
        --source examples/python-3.11.9/src/python \
        --platform windows-x86_64 \
        --repo-url https://github.com/vx-org/vx-rez-packages

The source tree must contain ``package.py``; its ``name`` and ``version``
globals are read to derive the bundle identity. The script writes, under
``bundles/<platform>/<name>/<version>/``:

    bundle.json          metadata plus the asset list
    assets/<file-name>   tar.gz and zip archives with identical members

Both archives wrap a single top-level ``<name>/<version>/`` directory holding
``package.py`` and the payload, which is exactly what ``vx-rez-adapter`` expects
to find under a package root.

Archives are written deterministically (sorted members, fixed mtime) so that
rebuilding an unchanged source reproduces the same bytes and checksum.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SPEC_VERSION = "1.0.0-draft"
GENERATOR = "make_bundle.py/1.0"
REPO_URL = "https://github.com/vx-org/vx-rez-packages"

# Fixed timestamp keeps archives byte-reproducible across rebuilds.
EPOCH = 1_700_000_000

PLATFORMS = (
    "windows-x86_64",
    "windows-aarch64",
    "windows-x86",
    "linux-x86_64",
    "linux-aarch64",
    "linux-x86",
    "macos-x86_64",
    "macos-aarch64",
)


class BundleError(RuntimeError):
    """Raised when a source tree cannot be turned into a valid bundle."""


@dataclass(frozen=True)
class PackageIdentity:
    """The name/version pair read out of a ``package.py``."""

    name: str
    version: str

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", self.name):
            raise BundleError(f"invalid package name {self.name!r}")
        if not re.fullmatch(r"[0-9]+(\.[0-9]+)*", self.version):
            raise BundleError(f"invalid package version {self.version!r}")


def read_identity(package_file: Path) -> PackageIdentity:
    """Read ``name`` and ``version`` from a ``package.py`` without importing it.

    ``package.py`` is Rez-authored Python that references undefined globals such
    as ``env``, so executing it here would fail. Only the two assignment
    statements this bundler needs are read.
    """
    if not package_file.is_file():
        raise BundleError(f"no package.py under {package_file.parent}")

    source = package_file.read_text(encoding="utf-8")
    values: dict[str, str] = {}
    for key in ("name", "version"):
        match = re.search(
            rf"^{key}\s*=\s*[\"']([^\"']+)[\"']\s*$", source, re.MULTILINE
        )
        if match is None:
            raise BundleError(f"{package_file} does not define {key!r}")
        values[key] = match.group(1)

    identity = PackageIdentity(name=values["name"], version=values["version"])
    identity.validate()
    return identity


def iter_members(source: Path, prefix: str):
    """Yield ``(absolute_path, archive_path)`` for every file in ``source``."""
    files = sorted(p for p in source.rglob("*") if p.is_file())
    for path in files:
        archive_path = f"{prefix}/{path.relative_to(source).as_posix()}"
        yield path, archive_path


def build_tar_gz(source: Path, prefix: str) -> bytes:
    """Build a gzip tar archive of ``source`` under ``prefix``.

    The gzip header carries its own mtime field, so a fixed tar mtime alone does
    not make the archive reproducible; the deflate stream is produced through
    ``gzip.GzipFile`` with ``mtime=0`` to pin it.
    """
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for path, archive_path in iter_members(source, prefix):
            info = tar.gettarinfo(str(path), arcname=archive_path)
            info.mtime = EPOCH
            info.mode = 0o755 if path.suffix == ".exe" else 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with path.open("rb") as handle:
                tar.addfile(info, handle)

    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", compresslevel=9, mtime=0) as gz:
        gz.write(raw.getvalue())
    return out.getvalue()


def build_zip(source: Path, prefix: str) -> bytes:
    """Build a zip archive of ``source`` under ``prefix``."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, archive_path in iter_members(source, prefix):
            info = zipfile.ZipInfo(archive_path, date_time=(2023, 11, 14, 22, 13, 20))
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    return buffer.getvalue()


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def version_sort_key(version: str) -> tuple:
    return tuple(int(part) for part in version.split("."))


def build_bundle(
    repo_root: Path,
    source: Path,
    platform: str,
    repo_url: str = REPO_URL,
    source_meta: dict | None = None,
) -> Path:
    """Write a bundle for ``source`` and return its ``bundle.json`` path."""
    if platform not in PLATFORMS:
        raise BundleError(f"unknown platform {platform!r}; expected one of {PLATFORMS}")

    identity = read_identity(source / "package.py")
    prefix = f"{identity.name}/{identity.version}"

    bundle_dir = repo_root / "bundles" / platform / identity.name / identity.version
    assets_dir = bundle_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    tag = f"{identity.name}-{identity.version}-{platform}"
    archives = {
        "tar.gz": build_tar_gz(source, prefix),
        "zip": build_zip(source, prefix),
    }

    assets = []
    for fmt, payload in archives.items():
        file_name = f"{tag}.{fmt}"
        (assets_dir / file_name).write_bytes(payload)
        assets.append(
            {
                "file_name": file_name,
                "format": fmt,
                "url": f"{repo_url.rstrip('/')}/releases/download/{tag}/{file_name}",
                "size": len(payload),
                "sha256": sha256(payload),
            }
        )

    bundle = {
        "spec_version": SPEC_VERSION,
        "name": identity.name,
        "version": identity.version,
        "platform": platform,
        "rez": {
            "layout": "rez-package-root",
            "package_root": prefix,
            "install_root": prefix,
            "package_file": "package.py",
        },
        "assets": assets,
        "requires": read_requires(source / "package.py"),
        "commands": read_commands(source),
        "build": {
            "requirement": f"{identity.name}-{identity.version}",
            "generator": GENERATOR,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    }
    if source_meta:
        bundle["build"]["source"] = source_meta

    bundle_file = bundle_dir / "bundle.json"
    bundle_file.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    return bundle_file


def read_requires(package_file: Path) -> list[str]:
    """Read the ``requires`` list from a ``package.py`` without executing it."""
    match = re.search(r"^requires\s*=\s*\[(.*?)\]", package_file.read_text(encoding="utf-8"), re.MULTILINE | re.DOTALL)
    if match is None:
        return []
    return re.findall(r"[\"']([^\"']+)[\"']", match.group(1))


def read_commands(source: Path) -> list[dict]:
    """Derive the command list from executable files beside ``package.py``."""
    commands = []
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.name == "package.py":
            continue
        if path.suffix.lower() in {".exe", ".bat", ".cmd"} or path.suffix == "":
            commands.append(
                {
                    "name": path.stem if path.suffix.lower() == ".exe" else path.name,
                    "relative_path": path.relative_to(source).as_posix(),
                }
            )
    return commands


def discover_bundles(repo_root: Path) -> list[tuple[Path, str, str, str]]:
    """Return ``(bundle_dir, platform, name, version)`` for every bundle on disk.

    Directories that are not valid vx platform keys are skipped: ``bundles/``
    holds only platform directories, but a stray directory must not silently
    become an entry in the index.
    """
    bundles_root = repo_root / "bundles"
    if not bundles_root.is_dir():
        return []

    found = []
    for platform_dir in sorted(p for p in bundles_root.iterdir() if p.is_dir()):
        if platform_dir.name not in PLATFORMS:
            continue
        for name_dir in sorted(p for p in platform_dir.iterdir() if p.is_dir()):
            for version_dir in sorted(p for p in name_dir.iterdir() if p.is_dir()):
                if (version_dir / "bundle.json").is_file():
                    found.append(
                        (version_dir, platform_dir.name, name_dir.name, version_dir.name)
                    )
    return found


def recompute_index(bundles: list) -> dict:
    """Build the index payload from a discovered bundle list."""
    packages: dict[str, dict] = {}
    platforms: set[str] = set()

    for _bundle_dir, platform, name, version in bundles:
        platforms.add(platform)
        entry = packages.setdefault(
            name, {"name": name, "versions": set(), "platforms": set()}
        )
        entry["versions"].add(version)
        entry["platforms"].add(platform)

    packages_out = []
    for entry in packages.values():
        versions = sorted(entry["versions"], key=version_sort_key)
        pkg_platforms = sorted(entry["platforms"])
        packages_out.append(
            {
                "name": entry["name"],
                "versions": versions,
                "platforms": pkg_platforms,
                "bundle": f"bundles/{pkg_platforms[0]}/{entry['name']}/{versions[-1]}/bundle.json",
            }
        )
    packages_out.sort(key=lambda p: p["name"])

    return {"platforms": sorted(platforms), "packages": packages_out}


def regenerate_index(repo_root: Path) -> Path:
    """Rewrite ``index.json`` from the bundle tree on disk."""
    payload = recompute_index(discover_bundles(repo_root))

    index = {
        "spec_version": SPEC_VERSION,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platforms": payload["platforms"],
        "packages": payload["packages"],
    }

    index_file = repo_root / "index.json"
    index_file.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return index_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, type=Path, help="rez package tree containing package.py")
    parser.add_argument("--platform", required=True, choices=PLATFORMS, help="vx platform key")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parent.parent, help="repository root")
    parser.add_argument("--repo-url", default=REPO_URL, help="repository base URL")
    parser.add_argument("--source-type", help="value for build.source.type")
    parser.add_argument("--source-version", help="value for build.source.version")
    parser.add_argument("--no-index", action="store_true", help="skip index.json regeneration")
    args = parser.parse_args(argv)

    source = args.source.resolve()
    if not source.is_dir():
        print(f"error: source directory not found: {source}", file=sys.stderr)
        return 1

    source_meta = None
    if args.source_type or args.source_version:
        source_meta = {"type": args.source_type, "version": args.source_version}

    try:
        bundle_file = build_bundle(args.repo_root.resolve(), source, args.platform, args.repo_url, source_meta)
        if not args.no_index:
            index_file = regenerate_index(args.repo_root.resolve())
            print(f"wrote {index_file.relative_to(args.repo_root.resolve())}")
    except BundleError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    print(f"wrote {bundle_file.relative_to(args.repo_root.resolve())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
