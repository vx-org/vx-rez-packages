"""Bidirectional keyset comparator and the explicit evidence gate (PIP-4717 B).

The comparison ``config_schema`` keys == rez 3.4.0 ``rezconfig.py`` keys needs
two independently sourced key lists. Neither authoritative list is available in
this task environment (see ``MISSING_EVIDENCE`` and ``EVIDENCE_GAP.md``). The
comparator below is complete and ready to run, but the real bidirectional test
is deliberately NOT executed and must never be reported as passed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

SCHEMA_SOURCE_ENV = "REZNEXT_SCHEMA_KEYS"
REFERENCE_SOURCE_ENV = "REZ_340_REZCONFIG_KEYS"

MISSING_EVIDENCE = (
    "the authoritative rez 3.4.0 `src/rez/rezconfig.py` complete key list is not "
    "vendored in this task environment; the only `rezconfig.py` present is "
    "rez-next's own compatibility module (same side, not an independent "
    "reference). `crates/rez-next-config/src/keys.rs` transcribes just 4 default "
    "values and its `test_all_divergent_keys_are_registered` is one-directional "
    "(DIVERGENT_KEYS subset-of registry). No synthetic fake key list is used."
)


def load_keys(env_var: str) -> list[str] | None:
    """Load an authoritative key list from a JSON file named by ``env_var``."""
    path = os.environ.get(env_var)
    if not path or not Path(path).is_file():
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
        raise ValueError(f"{env_var} must point to a JSON array of strings")
    return payload


def compare_keysets(schema_keys: list[str], reference_keys: list[str]) -> dict[str, list[str]]:
    """Return both directional diffs; both must be empty for equality."""
    schema = set(schema_keys)
    reference = set(reference_keys)
    return {
        "missing_in_schema": sorted(reference - schema),
        "missing_in_reference": sorted(schema - reference),
    }


def keysets_equal(schema_keys: list[str], reference_keys: list[str]) -> bool:
    """True only when neither directional diff has any key."""
    diff = compare_keysets(schema_keys, reference_keys)
    return not diff["missing_in_schema"] and not diff["missing_in_reference"]
