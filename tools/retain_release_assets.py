"""Retain pinned original archives alongside a release without altering their bytes."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import BinaryIO

from tools.build_bundle import (
    BundleError,
    _collision_key,
    _safe_relative,
    load_definition,
    validate_definition,
)

MANIFEST_NAME = "release-assets.json"
CHUNK_SIZE = 1024 * 1024


def _validate_https(url: str) -> None:
    try:
        parsed = urllib.parse.urlsplit(url)
        valid = (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and "#" not in url
            and parsed.port != 0
            and not any(character.isspace() or ord(character) < 32 for character in url)
            and "\\" not in url
        )
    except ValueError as error:
        raise BundleError("retained asset URL is malformed") from error
    if not valid:
        raise BundleError("retained asset URL requires HTTPS without credentials or fragments")


class _HttpsRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        # Validate before urllib sends the redirected request, including intermediate hops.
        _validate_https(new_url)
        return super().redirect_request(request, response, code, message, headers, new_url)


def _release_assets(definition: dict) -> list[dict]:
    assets = definition.get("release_assets", [])
    names: set[str] = set()
    for asset in assets:
        name = asset["name"]
        safe_name = _safe_relative(name)
        folded = _collision_key(name)
        if (
            safe_name != name
            or "/" in name
            or ".rez.tar.zst" in folded
            or folded.startswith(("index.json", MANIFEST_NAME))
        ):
            raise BundleError(f"reserved or non-flat retained asset name: {name!r}")
        _validate_https(asset["url"])
        for filename in (name, f"{name}.sha256"):
            key = _collision_key(filename)
            if key in names:
                raise BundleError(f"duplicate retained asset or checksum filename: {filename!r}")
            names.add(key)
    return sorted(assets, key=lambda asset: (_collision_key(asset["name"]), asset["name"]))


def _is_regular_file(path: Path) -> bool:
    return not path.is_symlink() and path.is_file()


def _verify_file(path: Path, expected_sha256: str, expected_size: int) -> None:
    if not _is_regular_file(path):
        raise BundleError(f"retained asset must be a regular file: {path.name}")
    if path.stat().st_size != expected_size:
        raise BundleError(f"retained asset size mismatch: {path.name}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected_sha256:
        raise BundleError(f"retained asset checksum mismatch: {path.name}")


def _install_temporary(temporary: Path, destination: Path, digest: str, size: int) -> None:
    try:
        # A same-directory hard link installs the complete verified file without replacing
        # an existing destination, including one created after the initial cache check.
        os.link(temporary, destination)
    except FileExistsError:
        _verify_file(destination, digest, size)


def _copy_verified(stream: BinaryIO, destination: Path, digest: str, size: int) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".retain-", suffix=".part", dir=destination.parent, delete=False
        ) as output:
            temporary = Path(output.name)
            actual_size = 0
            actual_digest = hashlib.sha256()
            while chunk := stream.read(min(CHUNK_SIZE, size - actual_size + 1)):
                actual_size += len(chunk)
                if actual_size > size:
                    raise BundleError(f"retained asset exceeds pinned size: {destination.name}")
                actual_digest.update(chunk)
                output.write(chunk)
            if actual_size != size:
                raise BundleError(f"retained asset size mismatch: {destination.name}")
            if actual_digest.hexdigest() != digest:
                raise BundleError(f"retained asset checksum mismatch: {destination.name}")
            output.flush()
            os.fsync(output.fileno())
        _install_temporary(temporary, destination, digest, size)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _write_exact(destination: Path, content: bytes) -> None:
    digest = hashlib.sha256(content).hexdigest()
    if destination.exists() or destination.is_symlink():
        _verify_file(destination, digest, len(content))
        return
    _copy_verified(io.BytesIO(content), destination, digest, len(content))


def _retain_one(asset: dict, output: Path, source_directory: Path | None) -> None:
    destination = output / asset["name"]
    if destination.exists() or destination.is_symlink():
        _verify_file(destination, asset["sha256"], asset["size"])
    else:
        source = source_directory / asset["name"] if source_directory is not None else None
        if source is not None and (source.exists() or source.is_symlink()):
            _verify_file(source, asset["sha256"], asset["size"])
            with source.open("rb") as stream:
                _copy_verified(stream, destination, asset["sha256"], asset["size"])
        else:
            request = urllib.request.Request(
                asset["url"], headers={"User-Agent": "vx-rez-packages/1"}
            )
            opener = urllib.request.build_opener(_HttpsRedirectHandler())
            with opener.open(request, timeout=60) as response:
                _validate_https(response.url)
                _copy_verified(response, destination, asset["sha256"], asset["size"])
    _write_exact(
        output / f"{asset['name']}.sha256",
        f"{asset['sha256']}  {asset['name']}\n".encode(),
    )


def retain_release_assets(
    definition: dict, output_directory: Path, *, source_directory: Path | None = None
) -> Path:
    """Keep exact pinned originals and companions, failing closed on conflicting files."""
    validate_definition(definition)
    assets = _release_assets(definition)
    content = (
        json.dumps({"schema_version": 1, "assets": assets}, indent=2, sort_keys=True) + "\n"
    ).encode()
    planned = {asset["name"]: (asset["sha256"], asset["size"]) for asset in assets}
    for asset in assets:
        checksum = f"{asset['sha256']}  {asset['name']}\n".encode()
        planned[f"{asset['name']}.sha256"] = (hashlib.sha256(checksum).hexdigest(), len(checksum))
    manifest_checksum = f"{hashlib.sha256(content).hexdigest()}  {MANIFEST_NAME}\n".encode()
    planned[MANIFEST_NAME] = (hashlib.sha256(content).hexdigest(), len(content))
    planned[f"{MANIFEST_NAME}.sha256"] = (
        hashlib.sha256(manifest_checksum).hexdigest(),
        len(manifest_checksum),
    )
    if output_directory.is_symlink():
        raise BundleError("retained asset output directory must not be a symlink")
    output_directory.mkdir(parents=True, exist_ok=True)
    portable_names = {_collision_key(name): name for name in planned}
    for existing in output_directory.iterdir():
        name = portable_names.get(_collision_key(existing.name))
        if name is None:
            continue
        if name != existing.name:
            raise BundleError(f"retained asset conflicts with an existing portable name: {name}")
        _verify_file(existing, *planned[name])
    for asset in assets:
        _retain_one(asset, output_directory, source_directory)
    manifest = output_directory / MANIFEST_NAME
    _write_exact(manifest, content)
    _write_exact(
        output_directory / f"{MANIFEST_NAME}.sha256",
        manifest_checksum,
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path)
    args = parser.parse_args()
    try:
        retain_release_assets(
            load_definition(args.definition),
            args.output_dir,
            source_directory=args.source_dir,
        )
    except (BundleError, OSError) as error:
        parser.exit(1, f"retained release asset verification failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
