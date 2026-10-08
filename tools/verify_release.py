"""Compare downloaded draft release assets with the fully validated local release."""

from __future__ import annotations

import argparse
from pathlib import Path

from tools.build_bundle import BundleError, _sha256


def verify_release(expected_directory: Path, downloaded_directory: Path) -> None:
    """Require exactly the expected files and bytes before making a draft public."""
    expected = {path.name: path for path in expected_directory.iterdir() if path.is_file()}
    downloaded = {path.name: path for path in downloaded_directory.iterdir() if path.is_file()}
    if not expected or set(expected) != set(downloaded):
        raise BundleError("uploaded draft release asset names differ from the validated release")
    for name, path in expected.items():
        if _sha256(path) != _sha256(downloaded[name]):
            raise BundleError(f"uploaded draft release checksum mismatch: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-dir", type=Path, required=True)
    parser.add_argument("--downloaded-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        verify_release(args.expected_dir, args.downloaded_dir)
    except (BundleError, OSError) as error:
        parser.exit(1, f"draft release verification failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
