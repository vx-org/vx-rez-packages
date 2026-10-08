#!/usr/bin/env python3
"""Create GitHub releases and upload bundle assets.

For every bundle under ``bundles/``, this script creates a release tagged
``<name>-<version>-<platform>`` and uploads the archives listed in its
``bundle.json``. Bundles whose tag already exist are skipped, so re-running is
safe and only publishes what is new.

Before uploading, each archive is checked against its recorded ``size`` and
``sha256``; a mismatch aborts that bundle rather than publishing a corrupt
asset. After upload, the digest reported by GitHub is compared to the recorded
one, which covers verification step 6 of SPEC.md — the only check CI cannot
perform, because release assets of an unmerged branch do not exist yet.

Requires the `gh` CLI, authenticated with permission to create releases.

Usage
-----
    python scripts/release.py --dry-run    # report without changing anything
    python scripts/release.py              # create releases and upload assets
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = "vx-org/vx-rez-packages"


class ReleaseError(RuntimeError):
    """A bundle could not be released."""


def run(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, check=check)


def discover_bundles(repo_root: Path) -> list[Path]:
    """Return every ``bundle.json`` under ``bundles/``."""
    bundles_root = repo_root / "bundles"
    if not bundles_root.is_dir():
        return []
    return sorted(bundles_root.glob("*/*/*/bundle.json"))


def tag_for(bundle: dict) -> str:
    return f"{bundle['name']}-{bundle['version']}-{bundle['platform']}"


def release_exists(tag: str) -> bool:
    result = run(["gh", "release", "view", tag, "--repo", REPO], check=False)
    return result.returncode == 0


def verify_asset(asset: dict, archive: Path) -> None:
    """Check the archive on disk matches the recorded size and digest."""
    if not archive.is_file():
        raise ReleaseError(f"{asset['file_name']}: archive not found at {archive}")

    payload = archive.read_bytes()
    if len(payload) != asset["size"]:
        raise ReleaseError(
            f"{asset['file_name']}: size is {asset['size']} on record, {len(payload)} on disk"
        )

    digest = hashlib.sha256(payload).hexdigest()
    if digest != asset["sha256"].lower():
        raise ReleaseError(
            f"{asset['file_name']}: sha256 is {asset['sha256']} on record, {digest} on disk"
        )


def release_bundle(repo_root: Path, bundle_file: Path, dry_run: bool) -> str:
    """Release a single bundle. Returns a one-line status message."""
    bundle = json.loads(bundle_file.read_text(encoding="utf-8"))
    tag = tag_for(bundle)

    assets = []
    for asset in bundle["assets"]:
        archive = bundle_file.parent / "assets" / asset["file_name"]
        verify_asset(asset, archive)
        assets.append(archive)

    if release_exists(tag):
        return f"skip {tag}: release already exists"

    notes = (
        f"Rez bundle: {bundle['name']} {bundle['version']} ({bundle['platform']})\n\n"
        f"Unpacks to `<cache_root>/{bundle['rez']['install_root']}/` so that "
        "`<cache_root>` can be passed to `vx-rez-adapter` as a package path."
    )

    if dry_run:
        return f"would release {tag} with {len(assets)} asset(s)"

    run(
        [
            "gh", "release", "create", tag,
            "--repo", REPO,
            "--title", f"{bundle['name']} {bundle['version']} ({bundle['platform']})",
            "--notes", notes,
            *[str(a) for a in assets],
        ]
    )

    for asset in bundle["assets"]:
        result = run(
            [
                "gh", "release", "view", tag, "--repo", REPO,
                "--json", "assets", "-q",
                f'.assets[] | select(.name == "{asset["file_name"]}") | .digest',
            ],
            check=False,
        )
        digest = result.stdout.strip()
        if digest and not digest.endswith(asset["sha256"]):
            raise ReleaseError(
                f"{asset['file_name']}: uploaded digest {digest} does not match {asset['sha256']}"
            )

    return f"released {tag} with {len(assets)} asset(s)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parent.parent, help="repository root")
    parser.add_argument("--dry-run", action="store_true", help="report without creating releases")
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    bundles = discover_bundles(repo_root)
    if not bundles:
        print("no bundles found", file=sys.stderr)
        return 1

    if run(["gh", "--version"], check=False).returncode != 0:
        print("error: the `gh` CLI is required but was not found on PATH", file=sys.stderr)
        return 1

    failures = 0
    for bundle_file in bundles:
        try:
            print(release_bundle(repo_root, bundle_file, args.dry_run))
        except (ReleaseError, json.JSONDecodeError, KeyError) as err:
            failures += 1
            print(f"FAIL {bundle_file.relative_to(repo_root)}: {err}", file=sys.stderr)

    if failures:
        print(f"\n{failures} bundle(s) failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
