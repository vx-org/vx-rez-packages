"""Generate a vx provider index from local assets or a GitHub Release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import jsonschema

from tools.build_bundle import BundleError, load_definition

ROOT = Path(__file__).resolve().parents[1]
INDEX_SCHEMA = ROOT / "schema" / "release-index.schema.json"


def generate_index_from_directory(
    definition: dict,
    asset_directory: Path,
    *,
    repository: str,
    release_tag: str,
    generated_at: str | None = None,
) -> dict:
    """Generate and validate an index from a complete local release directory."""
    _validate_release_tag(definition, release_tag)
    assets = {}
    checksum_contents = {}
    for target in definition["targets"]:
        asset_name = _asset_name(definition, target)
        asset = asset_directory / asset_name
        checksum_file = asset_directory / f"{asset_name}.sha256"
        if not asset.is_file() or not checksum_file.is_file():
            raise BundleError(f"release assets are incomplete for {target['triple']}")
        checksum = _parse_checksum(checksum_file.read_text(encoding="utf-8"), asset_name)
        actual = _sha256(asset)
        if checksum != actual:
            raise BundleError(
                f"release asset checksum mismatch for {asset_name}: "
                f"expected {checksum}, got {actual}"
            )
        assets[asset_name] = {
            "name": asset_name,
            "browser_download_url": _release_url(repository, release_tag, asset_name),
        }
        checksum_contents[f"{asset_name}.sha256"] = checksum_file.read_text(encoding="utf-8")
    release = {"tag_name": release_tag, "assets": list(assets.values())}
    return generate_index_from_release(
        definition,
        release,
        checksum_contents,
        repository=repository,
        generated_at=generated_at,
    )


def generate_index_from_release(
    definition: dict,
    release: dict,
    checksum_contents: dict[str, str],
    *,
    repository: str,
    generated_at: str | None = None,
) -> dict:
    """Generate and validate an index from GitHub Release API metadata."""
    release_tag = release.get("tag_name")
    if not isinstance(release_tag, str) or not release_tag:
        raise BundleError("GitHub release metadata has no tag_name")
    _validate_release_tag(definition, release_tag)
    assets = {asset["name"]: asset for asset in release.get("assets", [])}
    bundles = []
    for target in sorted(definition["targets"], key=lambda item: item["triple"]):
        asset_name = _asset_name(definition, target)
        checksum_name = f"{asset_name}.sha256"
        asset = assets.get(asset_name)
        if asset is None or checksum_name not in checksum_contents:
            raise BundleError(f"GitHub release is missing {asset_name} or its checksum")
        bundles.append(
            {
                "tool": definition["tool"],
                "version": definition["version"],
                "platform": target["platform"],
                "arch": target["arch"],
                "triple": target["triple"],
                "asset_name": asset_name,
                "download_url": asset["browser_download_url"],
                "sha256": _parse_checksum(checksum_contents[checksum_name], asset_name),
                "bundle_schema_version": 1,
                "package_root": f"{definition['tool']}/{definition['version']}",
            }
        )

    index = {
        "schema_version": 1,
        "generated_at": generated_at or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "repository": repository,
        "release_tag": release_tag,
        "bundles": bundles,
        "unsupported_targets": definition["unsupported_targets"],
    }
    _validate_index(index)
    return index


def fetch_github_release(repository: str, release_tag: str) -> tuple[dict, dict[str, str]]:
    """Fetch one GitHub Release and all required checksum companions."""
    encoded_tag = urllib.parse.quote(release_tag, safe="")
    release = _read_json_url(
        f"https://api.github.com/repos/{repository}/releases/tags/{encoded_tag}"
    )
    checksums = {}
    for asset in release.get("assets", []):
        if asset.get("name", "").endswith(".sha256"):
            checksums[asset["name"]] = _read_text_url(asset["browser_download_url"])
    return release, checksums


def write_index(index: dict, output: Path) -> None:
    """Write an index and an adjacent checksum file."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = _sha256(output)
    output.with_name(f"{output.name}.sha256").write_text(
        f"{digest}  {output.name}\n", encoding="utf-8"
    )


def _asset_name(definition: dict, target: dict) -> str:
    return f"{definition['tool']}-{definition['version']}-{target['triple']}.rez.tar.zst"


def _validate_release_tag(definition: dict, release_tag: str) -> None:
    expected = f"{definition['tool']}-{definition['version']}"
    if release_tag != expected:
        raise BundleError(f"release tag mismatch: expected {expected!r}, got {release_tag!r}")


def _release_url(repository: str, release_tag: str, asset_name: str) -> str:
    tag = urllib.parse.quote(release_tag, safe="")
    asset = urllib.parse.quote(asset_name, safe="")
    return f"https://github.com/{repository}/releases/download/{tag}/{asset}"


def _parse_checksum(content: str, expected_name: str) -> str:
    parts = content.strip().split()
    if len(parts) != 2 or parts[1].lstrip("*") != expected_name:
        raise BundleError(f"invalid checksum companion for {expected_name}")
    digest = parts[0].lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise BundleError(f"invalid SHA-256 digest for {expected_name}")
    return digest


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_index(index: dict) -> None:
    schema = json.loads(INDEX_SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )
    errors = sorted(validator.iter_errors(index), key=lambda error: list(error.path))
    if errors:
        raise BundleError(
            "release index validation failed: " + "; ".join(e.message for e in errors)
        )


def _request(url: str) -> urllib.request.Request:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "vx-rez-packages/1"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def _read_json_url(url: str) -> dict:
    return json.loads(_read_text_url(url))


def _read_text_url(url: str) -> str:
    try:
        with urllib.request.urlopen(_request(url), timeout=60) as response:  # noqa: S310
            return response.read().decode("utf-8")
    except OSError as error:
        raise BundleError(f"failed to read {url}: {error}") from error


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--asset-dir", type=Path)
    source.add_argument("--github-release-tag")
    parser.add_argument("--repository", default="vx-org/vx-rez-packages")
    parser.add_argument("--release-tag")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    definition = load_definition(args.definition)
    if args.asset_dir:
        if not args.release_tag:
            raise SystemExit("--release-tag is required with --asset-dir")
        index = generate_index_from_directory(
            definition,
            args.asset_dir,
            repository=args.repository,
            release_tag=args.release_tag,
        )
    else:
        release, checksums = fetch_github_release(args.repository, args.github_release_tag)
        index = generate_index_from_release(
            definition,
            release,
            checksums,
            repository=args.repository,
        )
    write_index(index, args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
