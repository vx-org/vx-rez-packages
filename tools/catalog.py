"""Discover pinned release indexes across independently maintained runtime repositories.

Catalog selection uses an exact runtime name and version. Rez Next owns package
requirements, variants, dependency resolution, and environment commands.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from pathlib import Path
from urllib.parse import urlsplit

import jsonschema
import zstandard

from tools import cache_bundle

CATALOG_SCHEMA = Path(__file__).resolve().parents[1] / "schema/catalog.schema.json"


class CatalogError(cache_bundle.CacheError):
    """A catalog's format or exact release selection is invalid."""


def _validate_https_url(value: str, label: str) -> None:
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname is not None
            and parsed.username is None
            and parsed.password is None
            and not parsed.fragment
            and "\\" not in value
            and not any(character.isspace() for character in value)
        )
        _ = parsed.port  # Reject malformed or out-of-range ports.
    except ValueError as error:
        raise CatalogError(f"{label} must be an absolute HTTPS URL") from error
    if not valid:
        raise CatalogError(f"{label} must be an absolute HTTPS URL without credentials or fragment")


def validate_catalog(catalog: dict) -> None:
    """Validate schema v1 and reject every repeated (tool, version) identity."""
    schema = json.loads(CATALOG_SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    errors = sorted(validator.iter_errors(catalog), key=lambda error: str(list(error.path)))
    if errors:
        raise CatalogError("catalog validation failed: " + "; ".join(e.message for e in errors))
    identities: set[tuple[str, str]] = set()
    for release in catalog["releases"]:
        identity = (release["tool"], release["version"])
        if identity in identities:
            raise CatalogError(f"duplicate catalog release: {identity[0]}@{identity[1]}")
        identities.add(identity)
        _validate_https_url(release["index_url"], "release index URL")


def _unique_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise CatalogError(f"duplicate catalog JSON key: {key}")
        result[key] = value
    return result


def load_catalog(path: Path) -> dict:
    """Read a catalog without accepting ambiguous, repeated JSON object keys."""
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_keys)
    except json.JSONDecodeError as error:
        raise CatalogError(f"invalid catalog JSON: {error}") from error
    validate_catalog(catalog)
    return catalog


def generate_catalog(releases: list[dict]) -> dict:
    """Validate reviewed release records and return a deterministic catalog."""
    catalog = {"schema_version": 1, "releases": releases}
    validate_catalog(catalog)
    return {
        "schema_version": 1,
        "releases": [
            dict(release)
            for release in sorted(
                releases, key=lambda release: (release["tool"], release["version"])
            )
        ],
    }


def write_catalog(catalog: dict, output: Path) -> None:
    """Write canonical UTF-8/LF bytes and an adjacent SHA-256 companion."""
    validate_catalog(catalog)
    canonical = generate_catalog(catalog["releases"])
    contents = (json.dumps(canonical, indent=2, sort_keys=True) + "\n").encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(contents)
    digest = hashlib.sha256(contents).hexdigest()
    output.with_name(f"{output.name}.sha256").write_bytes(f"{digest}  {output.name}\n".encode())


def provision_from_catalog(
    catalog_url: str,
    catalog_sha256: str,
    cache: Path,
    *,
    tool: str,
    version: str,
    platform: str,
    arch: str,
    offline: bool = False,
) -> Path:
    """Return a verified repository through one exact, pinned catalog release."""
    _validate_https_url(catalog_url, "catalog URL")
    catalog_path = cache_bundle._checked_download(
        catalog_url, catalog_sha256, cache / "catalogs" / catalog_sha256, offline=offline
    )
    catalog = load_catalog(catalog_path)
    matches = [
        release
        for release in catalog["releases"]
        if (release["tool"], release["version"]) == (tool, version)
    ]
    if len(matches) != 1:
        raise CatalogError(
            f"expected exactly one catalog release for {tool}@{version}; found {len(matches)}"
        )
    selected = matches[0]
    return cache_bundle.provision(
        selected["index_url"],
        selected["index_sha256"],
        cache,
        tool=tool,
        version=version,
        platform=platform,
        arch=arch,
        offline=offline,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="canonicalize a reviewed local catalog")
    generate.add_argument("--input", type=Path, required=True)
    generate.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate", help="validate a local catalog")
    validate.add_argument("--input", type=Path, required=True)
    cache = commands.add_parser("cache", help="cache one exact release from a pinned catalog")
    for option in ("catalog-url", "catalog-sha256", "tool", "version", "platform", "arch"):
        cache.add_argument(f"--{option}", required=True)
    cache.add_argument("--cache", type=Path, required=True)
    cache.add_argument("--offline", action="store_true")
    args = vars(parser.parse_args())
    command = args.pop("command")
    try:
        if command == "cache":
            print(provision_from_catalog(**args))
        else:
            catalog = load_catalog(args["input"])
            if command == "generate":
                write_catalog(catalog, args["output"])
                print(args["output"])
    except (
        cache_bundle.CacheError,
        OSError,
        ValueError,
        jsonschema.ValidationError,
        tarfile.TarError,
        zstandard.ZstdError,
    ) as error:
        parser.exit(1, f"catalog operation failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
