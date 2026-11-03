"""Supplementary synthetic model of the REZ_* override branches.

This is a deliberately small, behaviour-faithful replica kept from the first
PIP-4717 delivery. It is NOT the production implementation and its tests are
NOT the acceptance evidence: the authoritative A1-A4 coverage is now locked by
named Rust tests in ``crates/rez-next-common/src/config.rs`` (a verbatim copy of
the real rez-next file with only the four P3 fixes) and run with ``cargo test``
through ``rust_probe/``.

The earlier "synthetic fixtures only" constraint limited test data and isolated
copies; it never authorised substituting a Python port for the real Rust source.
This module is retained only as a secondary cross-check and as evidence of the
prior harness, not as a replacement for the production fix.
"""

from __future__ import annotations

import dataclasses
import sys
import threading
from typing import Any


class ConfigOverrideError(Exception):
    """Raised when an environment override cannot be applied."""


@dataclasses.dataclass
class CacheConfig:
    """Mirror the four fields of the Rust ``CacheConfig`` struct."""

    enable_memory_cache: bool = True
    enable_disk_cache: bool = True
    memory_cache_size: int = 1000
    cache_ttl_seconds: int = 3600


# Corrected wording for the stderr-report comment (finding A2). Upstream rez
# aborts with `ConfigurationError`; rez-next reports instead of failing hard.
REPORT_BEHAVIOR_COMMENT = (
    "Malformed REZ_* overrides are reported instead of failing hard: upstream rez "
    "raises `ConfigurationError` and aborts (src/rez/config.py), while rez-next "
    "keeps the previously loaded value and continues. The stderr report is NOT "
    "equivalent to rez's behaviour."
)

# Kept ONLY as the mutation target for the derived-keyword check (finding A3).
# The production path must never use this hardcoded list.
_HARDCODED_CACHE_KEYS = (
    "enable_memory_cache",
    "enable_disk_cache",
    "memory_cache_size",
    "cache_ttl_seconds",
)

_ENV_LOCK = threading.Lock()


def env_lock() -> threading.Lock:
    """Return the process-wide guard for tests that touch REZ_* variables."""
    return _ENV_LOCK


def load() -> dict[str, Any]:
    """Mirror ``RezCoreConfig::load()``; requires ``env_lock()`` to be held."""
    if not _ENV_LOCK.locked():
        raise ConfigOverrideError("load() requires env_lock() to be held")
    return {"version": "0.3.12"}


def format_expected_keys(base_keys: list[str]) -> str:
    """Render accepted cache keys from the *struct*, so the message cannot drift."""
    return ", ".join(base_keys)


def value_kind_name(value: Any) -> str:
    """Map a synthetic JSON value to the serde_json kind name used in config.rs."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "mapping"


def assign_cache(target: CacheConfig, value: Any) -> None:
    """Merge a REZ_CACHE_JSON value into ``target`` (config.rs ``assign_cache``).

    Unknown subkeys are rejected; a non-object value cannot silently reset the
    whole cache block. On any rejection ``target`` is left untouched.
    """
    base = dataclasses.asdict(target)
    if isinstance(value, dict):
        merged: Any = dict(base)
        for key, patch_value in value.items():
            if key not in base:
                raise ConfigOverrideError(
                    f"unknown cache key '{key}'; expected one of {format_expected_keys(list(base))}"
                )
            merged[key] = patch_value
    else:
        merged = value

    try:
        replacement = CacheConfig(**merged)
    except TypeError as exc:
        raise ConfigOverrideError(f"invalid cache override ({exc})") from exc

    for field in dataclasses.fields(CacheConfig):
        setattr(target, field.name, getattr(replacement, field.name))


def assign_path_list(target: list[str], value: Any) -> None:
    """Accept a JSON array of strings or a separator-delimited string."""
    if isinstance(value, list):
        paths = [item for item in value if isinstance(item, str)]
        if len(paths) != len(value):
            raise ConfigOverrideError("expected every path entry to be a string")
        target[:] = paths
        return
    if isinstance(value, str):
        target[:] = [part.strip() for part in value.split(":") if part.strip()]
        return
    raise ConfigOverrideError(f"expected a path list, got {value_kind_name(value)}")


def apply_env_overrides_and_report(messages: list[str]) -> None:
    """Print rejected overrides to stderr; the loader continues (does not abort)."""
    for message in messages:
        print(f"rez-next: ignoring {message}", file=sys.stderr)
