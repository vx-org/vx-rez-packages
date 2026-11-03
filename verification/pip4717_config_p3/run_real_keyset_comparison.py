"""Execute the real PIP-4717 B bidirectional keyset comparison.

Prints both directional diffs and exits **1** while strict equality is not
met. This is deliberately a failing command: the six documented keys are a
real, recorded divergence, not a missing input. A green exit here without the
keys being registered upstream would mean someone deleted keys or used the
same source on both sides.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Keep the harness importable under `python -I` (isolated mode does not prepend
# the script directory to sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent))

import keyset_invariant as ki  # noqa: E402


def main() -> int:
    sources = ki.load_real_key_sources()
    diff = ki.compare_keysets(sources.schema_keys, sources.reference_keys)

    print(f"schema source    : {sources.schema_path}")
    print(f"reference source : {sources.reference_path}")
    print(f"schema keys      : {len(sources.schema_keys)}")
    print(f"reference keys   : {len(sources.reference_keys)}")
    print(f"missing_in_schema ({len(diff['missing_in_schema'])}):")
    for key in diff["missing_in_schema"]:
        print(f"  - {key}")
    print(f"missing_in_reference ({len(diff['missing_in_reference'])}):")
    for key in diff["missing_in_reference"]:
        print(f"  - {key}")

    if ki.keysets_equal(sources.schema_keys, sources.reference_keys):
        print("RESULT: PASS (both directional diffs empty)")
        return 0

    if diff["missing_in_schema"] == list(ki.KNOWN_DIVERGENCE) and not diff["missing_in_reference"]:
        print(
            "RESULT: FAIL (expected documented divergence; see "
            "KEYSET_COMPATIBILITY.md). Strict equality is NOT satisfied."
        )
    else:
        print("RESULT: FAIL (NEW drift beyond the documented divergence)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
