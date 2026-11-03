"""Bidirectional keyset comparator for the PIP-4717 B invariant.

Two INDEPENDENT authoritative sources are vendored in this harness, read-only:

* upstream rez **3.4.0** ``src/rez/rezconfig.py`` (146 top-level settings);
* rez-next ``crates/rez-next-python/python/rez_next/config.py`` ``config_schema``
  (140 keys), from the rez-next #380 head ``2405006``.

The real bidirectional comparison **is executed** and it genuinely **FAILS**:
six upstream keys are absent from ``config_schema`` and the reverse diff is
empty. This is an honest, recorded divergence, not a missing input and not a
waiver. Nothing is deleted from either source to force a pass, and pointing
both inputs at the same file is rejected rather than producing a fake empty
diff. See ``KEYSET_COMPATIBILITY.md`` for the per-key policy.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REFERENCE_TREE = ROOT / "upstream" / "rez-3.4.0"
SCHEMA_TREE = ROOT / "upstream" / "rez-next@2405006"

REFERENCE_SOURCE = REFERENCE_TREE / "src" / "rez" / "rezconfig.py"
SCHEMA_SOURCE = SCHEMA_TREE / "crates" / "rez-next-python" / "python" / "rez_next" / "config.py"
# rez-next's own compatibility/defaults module: the SAME side as config_schema,
# so it is explicitly rejected as an independent reference.
SAME_SIDE_REZCONFIG = (
    SCHEMA_TREE / "crates" / "rez-next-python" / "python" / "rez_next" / "rezconfig.py"
)

# Retained for synthetic comparator tests only. The real comparison reads the
# vendored sources directly and never uses these environment variables.
SCHEMA_SOURCE_ENV = "REZNEXT_SCHEMA_KEYS"
REFERENCE_SOURCE_ENV = "REZ_340_REZCONFIG_KEYS"

# The exact FAIL result of the real comparison. Pinned so a new upstream key
# added without schema registration turns the divergence test red, and so
# deleting keys to force a pass also turns it red.
KNOWN_DIVERGENCE: tuple[str, ...] = (
    "debug_old_commands",
    "disable_rez_1_compatibility",
    "error_old_commands",
    "plugins",
    "rez_1_environment_variables",
    "warn_old_commands",
)

# SHA-256 of the two vendored authoritative sources. The repo commits LF blobs
# (``.gitattributes``: ``* text=auto eol=lf``); the first delivery pinned the
# CRLF-rendered digests by mistake, so both hash tests failed on a normal
# checkout. Hash EOL-normalized bytes (the LF form) as the primary pin and keep
# the CRLF-rendered digest as a second pin, so both conventions are explicit and
# the check is independent of the checkout's line endings. Pinning these proves
# no key was removed from, or injected into, either source to manufacture equality.
REFERENCE_SOURCE_SHA256 = "0bf79731e179ca0815b5364ffd810e23dbe7c974f2fd2aca78a0742b15778599"
SCHEMA_SOURCE_SHA256 = "eb812d59fed0f05d78862d6bc3f93cf58b1cd306708665f9304940fcbc23fb75"
REFERENCE_SOURCE_CRLF_SHA256 = "c634be4d326be7cf41d1545e3b00b0495074281f0e9e09e384ac69b0ba852e05"
SCHEMA_SOURCE_CRLF_SHA256 = "be12a3bd138cd021278d2ff48b45ea445a8fbc9da957da5a1abfc78f7c170c7b"


def normalize_line_endings(data: bytes) -> bytes:
    """Collapse CRLF/CR to LF so a content hash is EOL-independent."""
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def crlf_line_endings(data: bytes) -> bytes:
    """Render LF-normalized bytes as CRLF (the second pinned convention)."""
    return normalize_line_endings(data).replace(b"\n", b"\r\n")


def source_sha256(path: Path) -> str:
    """EOL-normalized SHA-256 of a vendored source file."""
    return hashlib.sha256(normalize_line_endings(Path(path).read_bytes())).hexdigest()


class SourceIndependenceError(ValueError):
    """Raised when the two key lists are not independently sourced."""


@dataclasses.dataclass(frozen=True)
class RealKeySources:
    """The two real key lists together with the files they were read from."""

    schema_keys: list[str]
    reference_keys: list[str]
    schema_path: Path
    reference_path: Path


def load_keys(env_var: str) -> list[str] | None:
    """Load an authoritative key list from a JSON file named by ``env_var``.

    Synthetic comparator tests use this. It never feeds the real comparison.
    """
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


def extract_rezconfig_keys(path: Path) -> list[str]:
    """AST-extract top-level simple-name settings from upstream ``rezconfig.py``.

    rez 3.4.0 declares every setting as a module-level ``name = value``
    assignment. Docstrings, imports and expressions are not settings.
    """
    tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename=str(path))
    return [
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    ]


def extract_schema_keys(path: Path) -> list[str]:
    """AST-extract the ``config_schema`` dict keys from rez-next ``config.py``."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "config_schema" for target in node.targets
        ):
            if not isinstance(node.value, ast.Dict):
                raise ValueError("config_schema is not a dict literal")
            keys = [
                key.value
                for key in node.value.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            ]
            if len(keys) != len(node.value.keys):
                raise ValueError("config_schema contains a non-string key")
            return keys
    raise ValueError(f"config_schema not found in {path}")


def assert_distinct_sources(schema_path: Path, reference_path: Path) -> None:
    """Reject identical paths or identical contents (a fake empty diff).

    Without this check two environment variables pointing at the same file
    produce an empty bidirectional diff and a passing test that proves nothing.
    """
    schema = Path(schema_path).resolve()
    reference = Path(reference_path).resolve()
    if not schema.is_file() or not reference.is_file():
        raise SourceIndependenceError("both key sources must be existing files")
    if schema == reference:
        raise SourceIndependenceError("schema and reference point at the same file")
    if schema.read_bytes() == reference.read_bytes():
        raise SourceIndependenceError("schema and reference have identical contents")


def assert_independent_sources(schema_path: Path, reference_path: Path) -> None:
    """Require two distinct files from the two different vendored trees.

    The reference must come from the upstream rez 3.4.0 tree and the schema
    from the rez-next tree. rez-next's own ``rezconfig.py`` compatibility
    module is the same side and is rejected as circular evidence.
    """
    assert_distinct_sources(schema_path, reference_path)
    schema = Path(schema_path).resolve()
    reference = Path(reference_path).resolve()
    if not schema.is_relative_to(SCHEMA_TREE.resolve()):
        raise SourceIndependenceError("schema source is not from the rez-next tree")
    if not reference.is_relative_to(REFERENCE_TREE.resolve()):
        raise SourceIndependenceError("reference source is not from the independent rez 3.4.0 tree")


def load_real_key_sources(
    schema_path: Path = SCHEMA_SOURCE,
    reference_path: Path = REFERENCE_SOURCE,
) -> RealKeySources:
    """Read both real key lists, refusing same-source or same-side inputs."""
    assert_independent_sources(schema_path, reference_path)
    return RealKeySources(
        schema_keys=extract_schema_keys(schema_path),
        reference_keys=extract_rezconfig_keys(reference_path),
        schema_path=Path(schema_path),
        reference_path=Path(reference_path),
    )


def load_keys_from_env() -> tuple[list[str], list[str]] | None:
    """Load both env-named key lists, refusing same-file/same-content inputs."""
    schema_path = os.environ.get(SCHEMA_SOURCE_ENV)
    reference_path = os.environ.get(REFERENCE_SOURCE_ENV)
    if not schema_path or not reference_path:
        return None
    assert_distinct_sources(Path(schema_path), Path(reference_path))
    schema = load_keys(SCHEMA_SOURCE_ENV)
    reference = load_keys(REFERENCE_SOURCE_ENV)
    if schema is None or reference is None:
        return None
    return schema, reference
