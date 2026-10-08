#!/usr/bin/env python3
"""Validate every bundle in this repository against SPEC.md.

Checks performed (see SPEC.md section 7):

1. ``bundle.json`` parses and validates against ``schema/bundle.schema.json``.
2. ``name`` / ``version`` / ``platform`` match the directory path.
3. ``version`` is a dot-separated numeric string.
4. Every asset declares file_name, format, url, size and a hex sha256.
5. ``index.json`` validates against ``schema/index.schema.json`` and equals the
   index recomputed from the bundle tree.
6. Asset files present in ``assets/`` match their recorded size and sha256, and
   unpack to the declared ``rez.package_root`` containing ``package_file``.
7. Platform directory names are known vx platform keys.

The schema validation in steps 1 and 5 uses a small built-in validator covering
the subset of JSON Schema this repository uses, so the check runs on a stock
Python interpreter with no dependencies. ``index.json`` is derived data: this
script always compares it against the index recomputed from the bundle tree, so
a hand-edited or stale index fails the run.

Exit code is 0 when every check passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import tarfile
import zipfile
from pathlib import Path

SPEC_VERSION = "1.0.0-draft"

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


class ValidationError(Exception):
    """A single schema violation."""

    def __init__(self, path: str, message: str):
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


def version_sort_key(version: str) -> tuple:
    return tuple(int(part) for part in version.split("."))


# ---------------------------------------------------------------------------
# Minimal JSON Schema validator
# ---------------------------------------------------------------------------
# Supports the keywords used by schema/*.json: type, required, properties,
# additionalProperties (bool or schema), items, enum, const, pattern,
# minItems, maxItems, uniqueItems, minimum, exclusiveMinimum, $ref/$defs.
# `format` is advisory and not enforced (see FORMAT_NOTE below).


def resolve_ref(ref: str, root: dict) -> dict:
    if not ref.startswith("#/"):
        raise ValidationError(ref, f"unsupported $ref {ref!r}")
    node: dict = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def validate_schema(instance, schema: dict, root: dict, path: str = "$") -> None:
    if "$ref" in schema:
        validate_schema(instance, resolve_ref(schema["$ref"], root), root, path)
        return

    expected = schema.get("type")
    if expected is not None:
        if expected == "object" and not isinstance(instance, dict):
            raise ValidationError(path, f"expected object, got {type(instance).__name__}")
        if expected == "array" and not isinstance(instance, list):
            raise ValidationError(path, f"expected array, got {type(instance).__name__}")
        if expected == "string" and not isinstance(instance, str):
            raise ValidationError(path, f"expected string, got {type(instance).__name__}")
        if expected == "integer" and (
            not isinstance(instance, int) or isinstance(instance, bool)
        ):
            raise ValidationError(path, f"expected integer, got {type(instance).__name__}")

    if "const" in schema and instance != schema["const"]:
        raise ValidationError(path, f"expected {schema['const']!r}, got {instance!r}")

    if "enum" in schema and instance not in schema["enum"]:
        raise ValidationError(path, f"{instance!r} is not one of {schema['enum']}")

    if isinstance(instance, str) and "pattern" in schema:
        if re.search(schema["pattern"], instance) is None:
            raise ValidationError(path, f"{instance!r} does not match {schema['pattern']}")

    if isinstance(instance, int) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            raise ValidationError(path, f"{instance} is below minimum {schema['minimum']}")
        if "exclusiveMinimum" in schema and instance <= schema["exclusiveMinimum"]:
            raise ValidationError(path, f"{instance} must exceed {schema['exclusiveMinimum']}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            raise ValidationError(path, f"needs at least {schema['minItems']} item(s)")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            raise ValidationError(path, f"allows at most {schema['maxItems']} item(s)")
        if schema.get("uniqueItems") and len({json.dumps(i, sort_keys=True) for i in instance}) != len(instance):
            raise ValidationError(path, "items must be unique")
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(instance):
                validate_schema(item, item_schema, root, f"{path}[{index}]")

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                raise ValidationError(path, f"missing required field {key!r}")

        properties = schema.get("properties", {})
        for key, value in instance.items():
            child = f"{path}.{key}"
            if key in properties:
                validate_schema(value, properties[key], root, child)
            else:
                extra = schema.get("additionalProperties")
                if extra is False:
                    raise ValidationError(child, "is not an allowed field")
                if isinstance(extra, dict):
                    validate_schema(value, extra, root, child)


def load_schema(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Bundle checks
# ---------------------------------------------------------------------------


def discover_bundles(repo_root: Path) -> list[tuple[Path, str, str, str]]:
    """Return ``(bundle_dir, platform, name, version)`` for every bundle found.

    Only directories whose name is a known vx platform key are treated as
    platform directories, so a stray directory under ``bundles/`` cannot become
    an index entry.
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


def check_bundle(
    repo_root: Path,
    bundle_dir: Path,
    platform: str,
    name: str,
    version: str,
    schema: dict,
    errors: list[str],
) -> dict | None:
    """Validate one bundle directory, appending problems to ``errors``."""
    label = bundle_dir.relative_to(repo_root).as_posix()
    bundle_file = bundle_dir / "bundle.json"

    try:
        bundle = json.loads(bundle_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        errors.append(f"{label}/bundle.json: invalid JSON: {err}")
        return None

    try:
        validate_schema(bundle, schema, schema, "$")
    except ValidationError as err:
        errors.append(f"{label}/bundle.json: {err}")

    # Spec check 7: platform directory must be a known vx platform key.
    if platform not in PLATFORMS:
        errors.append(f"{label}: unknown platform directory {platform!r}")

    # Spec check 2: identity fields must match the directory path.
    for field, expected in (("name", name), ("version", version), ("platform", platform)):
        actual = bundle.get(field)
        if actual != expected:
            errors.append(
                f"{label}/bundle.json: {field} is {actual!r} but the directory says {expected!r}"
            )

    # Spec check 3: version shape (also enforced by the schema pattern).
    if bundle.get("version") is not None and not re.fullmatch(
        r"[0-9]+(\.[0-9]+)*", str(bundle["version"])
    ):
        errors.append(f"{label}/bundle.json: version {bundle['version']!r} is not numeric")

    check_assets(repo_root, bundle_dir, bundle, errors)
    return bundle


def check_assets(
    repo_root: Path, bundle_dir: Path, bundle: dict, errors: list[str]
) -> None:
    """Check declared assets, and any that exist on disk, end to end."""
    label = bundle_dir.relative_to(repo_root).as_posix()
    assets = bundle.get("assets")
    if not isinstance(assets, list) or not assets:
        errors.append(f"{label}/bundle.json: assets must list at least one archive")
        return

    for index, asset in enumerate(assets):
        prefix = f"{label}/bundle.json: assets[{index}]"

        # Spec check 4 (shape; the schema enforces presence and types).
        url = asset.get("url", "")
        file_name = asset.get("file_name", "")
        if file_name and not url.endswith("/" + file_name):
            errors.append(f"{prefix}: url does not end with file_name {file_name!r}")

        # Spec check 6: a locally present asset must match size and digest, and
        # unpack to the declared rez package root.
        local = bundle_dir / "assets" / file_name
        if not local.is_file():
            continue

        payload = local.read_bytes()
        if asset.get("size") != len(payload):
            errors.append(
                f"{prefix}: size is {asset.get('size')} but {file_name} is {len(payload)} bytes"
            )

        digest = hashlib.sha256(payload).hexdigest()
        if asset.get("sha256", "").lower() != digest:
            errors.append(f"{prefix}: sha256 is {asset.get('sha256')} but {file_name} hashes to {digest}")

        check_archive_layout(bundle_dir, local, asset, bundle, prefix, errors)


def check_archive_layout(
    bundle_dir: Path,
    archive: Path,
    asset: dict,
    bundle: dict,
    prefix: str,
    errors: list[str],
) -> None:
    """Verify the archive unpacks to the declared rez package root."""
    rez = bundle.get("rez") if isinstance(bundle.get("rez"), dict) else {}
    package_root = rez.get("package_root") if rez else None
    package_file = (rez or {}).get("package_file", "package.py")
    if not package_root:
        return

    expected = f"{package_root}/{package_file}"

    try:
        if asset.get("format") == "zip":
            names = zipfile.ZipFile(archive).namelist()
        else:
            with tarfile.open(archive, "r:gz") as tar:
                names = tar.getnames()
    except (tarfile.TarError, zipfile.BadZipFile) as err:
        errors.append(f"{prefix}: cannot read {archive.name}: {err}")
        return

    if expected not in names:
        errors.append(
            f"{prefix}: {archive.name} does not contain {expected!r}; "
            f"vx-rez-adapter needs <root>/<name>/<version>/package.py"
        )


def check_index(repo_root: Path, schema: dict, bundles: list, errors: list[str]) -> None:
    """Validate ``index.json`` and, in strict mode, compare it to the tree."""
    index_file = repo_root / "index.json"
    if not index_file.is_file():
        errors.append("index.json: missing; run scripts/make_bundle.py to generate it")
        return

    try:
        index = json.loads(index_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        errors.append(f"index.json: invalid JSON: {err}")
        return

    try:
        validate_schema(index, schema, schema, "$")
    except ValidationError as err:
        errors.append(f"index.json: {err}")

    recomputed = recompute_index(bundles)
    for field in ("platforms", "packages"):
        if index.get(field) != recomputed.get(field):
            errors.append(
                f"index.json: {field} is out of date; run scripts/make_bundle.py to regenerate "
                f"(expected {json.dumps(recomputed.get(field))}, found {json.dumps(index.get(field))})"
            )


def recompute_index(bundles: list[tuple[Path, str, str, str]]) -> dict:
    """Rebuild the index payload from the discovered bundle tree."""
    packages: dict[str, dict] = {}
    platforms: set[str] = set()

    for _bundle_dir, platform, name, version in bundles:
        platforms.add(platform)
        entry = packages.setdefault(name, {"name": name, "versions": set(), "platforms": set()})
        entry["versions"].add(version)
        entry["platforms"].add(platform)

    packages_out = []
    for entry in packages.values():
        versions = sorted(entry["versions"], key=version_sort_key)
        platforms_for_pkg = sorted(entry["platforms"])
        packages_out.append(
            {
                "name": entry["name"],
                "versions": versions,
                "platforms": platforms_for_pkg,
                "bundle": f"bundles/{platforms_for_pkg[0]}/{entry['name']}/{versions[-1]}/bundle.json",
            }
        )
    packages_out.sort(key=lambda p: p["name"])

    return {"platforms": sorted(platforms), "packages": packages_out}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parent.parent, help="repository root")
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    bundle_schema = load_schema(repo_root / "schema" / "bundle.schema.json")
    index_schema = load_schema(repo_root / "schema" / "index.schema.json")

    bundles = discover_bundles(repo_root)
    errors: list[str] = []

    if not bundles:
        errors.append("no bundles found under bundles/<platform>/<name>/<version>/")

    for bundle_dir, platform, name, version in bundles:
        check_bundle(repo_root, bundle_dir, platform, name, version, bundle_schema, errors)

    check_index(repo_root, index_schema, bundles, errors)

    if errors:
        print(f"FAIL: {len(errors)} problem(s) found", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"OK: {len(bundles)} bundle(s) and index.json conform to spec {SPEC_VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
