# Bidirectional keyset invariant (PIP-4717 B): corrected state

**Status: EXECUTED. Currently FAILING strict equality. Not skipped, not
waived, not "only missing input".**

This file replaced the earlier `UNVERIFIED` claim of the first delivery. The
independent NACK review of `2647505` demonstrated that the authoritative
sources are already present locally, so the earlier "evidence unavailable"
statement was incorrect. The filename is kept for continuity; the current
result and full compatibility policy live in `KEYSET_COMPATIBILITY.md`.

## Required comparison

`config_schema` key set == rez 3.4.0 `src/rez/rezconfig.py` key set, with both
directional differences empty, and failing when a key is added to the key
registry without being registered in the schema.

## What is actually available

| Side | Vendored at | Keys |
| --- | --- | --- |
| Independent upstream rez 3.4.0 | `upstream/rez-3.4.0/src/rez/rezconfig.py` | 146 |
| rez-next `config_schema` | `upstream/rez-next@2405006/crates/rez-next-python/python/rez_next/config.py` | 140 |

Both are pre-existing local files from two different trees. AST extraction is
implemented in `keyset_invariant.py` (`extract_rezconfig_keys` /
`extract_schema_keys`); `assert_independent_sources()` rejects identical paths,
identical contents, swapped trees and rez-next's own same-side `rezconfig.py`.

## Result of the real run

`missing_in_schema` = 6 keys (`debug_old_commands`,
`disable_rez_1_compatibility`, `error_old_commands`, `plugins`,
`rez_1_environment_variables`, `warn_old_commands`);
`missing_in_reference` = empty. `keysets_equal()` is `False`.
`run_real_keyset_comparison.py` exits `1`;
`test_strict_bidirectional_keyset_equality` is an explicit expected failure.

No key was deleted from either source to force a pass (both SHA-256 values are
pinned and checked), and no source was reused for both sides. The six keys and
their per-key compatibility policy are documented in
`KEYSET_COMPATIBILITY.md`. Any new drift in either direction makes the
divergence test fail, which is the registry-addition guard.

## Commands

```bash
python -I verification/pip4717_config_p3/run_real_keyset_comparison.py   # exits 1, prints both diffs
python -m unittest discover -s verification/pip4717_config_p3 -v
```
