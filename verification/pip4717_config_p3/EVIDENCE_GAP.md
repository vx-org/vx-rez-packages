# Bidirectional keyset invariant (PIP-4717 B): exact missing evidence

**Status: UNVERIFIED. Not passed. Not waived.**

## Required comparison

`config_schema` key set == rez 3.4.0 `src/rez/rezconfig.py` key set, with both
directional differences empty (`reference - schema` and `schema - reference`),
and the test must fail when a key is added to the key registry without being
registered in the schema.

## What is missing

The **independent authoritative rez 3.4.0 `src/rez/rezconfig.py` complete key
list** is not present in this task environment. Specifically:

- The only `rezconfig.py` available in the rez-next checkout is
  `crates/rez-next-python/python/rez_next/rezconfig.py` — rez-next's *own*
  compatibility/defaults module. It is the **same side** of the comparison, so
  using it as the reference would be circular and would prove nothing.
- `crates/rez-next-python/python/rez_next/config.py` defines `config_schema`
  (140 keys) — again rez-next's own side, not an independent upstream source.
- `crates/rez-next-config/src/keys.rs` transcribes only **4** upstream default
  *values* (`upstream_3_4_0_defaults()`), not the complete upstream key list.
  `test_all_divergent_keys_are_registered` is one-directional
  (`DIVERGENT_KEYS` subset of `registry`), and
  `test_upstream_default_snapshot_stays_exhaustive` compares only the small
  subset of keys that have a rez default — neither is a full bidirectional
  keyset equality over `config_schema`.
- No vendored `src/rez/rezconfig.py`, exported key-list fixture, or pinned rez
  3.4.0 snapshot exists anywhere in the worktree or its resources. Fetching the
  upstream source is out of scope here (synthetic fixtures only; no installation
  or external acquisition authorised).

## What was delivered instead

- A real, executable **bidirectional comparator** (`keyset_invariant.py`):
  `compare_keysets()` returns both diffs and `keysets_equal()` requires both to
  be empty. `load_keys()` can ingest authoritative lists from
  `REZNEXT_SCHEMA_KEYS` and `REZ_340_REZCONFIG_KEYS` (JSON arrays of strings)
  once both sources are supplied; no synthetic fake list is substituted.
- `test_bidirectional_keyset_equality` is explicitly **skipped** with reason
  `UNVERIFIED (not passed): ...`, so it cannot be mistaken for a green result.
- The comparator's drift detection (both directions, and the "new registry key"
  case) is proven with **synthetic key sets** and covered by mutation checks.

## What must happen for the invariant to pass

Supply both authoritative key lists (the exported `config schema` key set and the
rez 3.4.0 `rezconfig.py` key list) as the two JSON files named above, then run:

```bash
python -m unittest verification/pip4717_config_p3/test_keyset_invariant.py -v
```

Only when both sources are independent and the skip condition lifts can the
bidirectional equality be executed and reported as passed. Until then this item
remains open in PIP-4717.
