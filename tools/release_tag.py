"""Print or check the immutable release tag declared by a runtime recipe."""

from __future__ import annotations

import argparse
from pathlib import Path

from tools.build_bundle import BundleError, expected_release_tag, load_definition


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", type=Path, required=True)
    parser.add_argument("--check", metavar="TAG")
    args = parser.parse_args()
    try:
        expected = expected_release_tag(load_definition(args.definition))
        if args.check is not None and args.check != expected:
            raise BundleError(f"release tag mismatch: expected {expected!r}, got {args.check!r}")
    except (BundleError, OSError, ValueError) as error:
        parser.exit(1, f"release tag validation failed: {error}\n")
    print(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
