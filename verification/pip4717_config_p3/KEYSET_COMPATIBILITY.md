# Bidirectional keyset comparison: executed result and compatibility policy

**Status: EXECUTED, currently FAILING strict equality.** This is not
`UNVERIFIED`, not "only missing input", not skipped and not waived.

## Sources (independent, vendored read-only)

| Side | File | SHA-256 prefix (LF-normalized) | Keys | Origin |
| --- | --- | --- | --- | --- |
| Reference | `upstream/rez-3.4.0/src/rez/rezconfig.py` | `0bf79731e179` | 146 | upstream rez 3.4.0 (`src/rez/utils/_version.py`) |
| Schema | `upstream/rez-next@2405006/crates/rez-next-python/python/rez_next/config.py` (`config_schema`) | `eb812d59fed0` | 140 | rez-next #380 head `2405006` |

Both are pre-existing local files in this workspace. Reading them needs no
network, installation or new credentials. They come from two different
trees, are byte-different, and are AST-extracted independently (top-level
`Name` assignments vs. the `config_schema` dict literal). Pointing both
inputs at one file, or using rez-next's own `rezconfig.py` compatibility
module as the reference, is rejected by `assert_independent_sources()`.

The repo commits LF blobs (`.gitattributes`: `* text=auto eol=lf`), so these
prefixes are the LF-normalized digests. `keyset_invariant.py` pins both the
LF-normalized and the CRLF-rendered form of each source and hashes
EOL-normalized bytes, so the pin is independent of the checkout's line endings.

## Actual result

```
missing_in_schema (6):
  - debug_old_commands
  - disable_rez_1_compatibility
  - error_old_commands
  - plugins
  - rez_1_environment_variables
  - warn_old_commands
missing_in_reference (0):
```

`keysets_equal()` is **False**. `test_strict_bidirectional_keyset_equality`
asserts two empty diffs and is decorated `@unittest.expectedFailure` because
the assertion genuinely fails; `run_real_keyset_comparison.py` exits `1`.

## Per-key compatibility policy

The six keys are **not removed from either source** to manufacture equality.
Their full SHA-256 is pinned in `keyset_invariant.py` — over LF-normalized
bytes, with the CRLF-rendered digest pinned as a second convention — checked by
`TestVendoredSourcesAreUnmodified` and each of the four pins by its own mutation
in `mutation_checks.py`, so deleting a key (or injecting a key) turns the suite
red regardless of checkout EOL. Any *new* key on either side also turns the
divergence test red, which is the "registry key added without schema
registration" guard.

| Key | Upstream rez 3.4.0 evidence | rez-next side | Policy |
| --- | --- | --- | --- |
| `warn_old_commands` | `rezconfig.py` "Rez-1 Compatibility" section; `.. deprecated:: 2.114.0`, "Will be removed in a future release" | Listed in `config.py::_deprecated_settings` (`_Deprecation("the future")`); absent from `config_schema` and `keys.rs` | Deprecated rez-1 command lint switch. rez-next has no rez-1 command execution path, so it deliberately does not validate the setting. Do not add a no-op validator. |
| `error_old_commands` | Same deprecated section; companion of `warn_old_commands` | Same `_deprecated_settings` entry; absent from schema/registry | Same as above. |
| `debug_old_commands` | Same deprecated section; upstream comment says "This currently has no effect" | Not referenced in `config.py` or `keys.rs` | Inert upstream debug flag; intentionally not modelled. |
| `rez_1_environment_variables` | Same deprecated section; controls legacy `REZ_*` environment variables | Same `_deprecated_settings` entry; absent from schema/registry | rez-1 environment-variable emission has no rez-next equivalent; intentionally not modelled. |
| `disable_rez_1_compatibility` | Same deprecated section; default changed to `True` in rez 3.0.0 "in preparation of future removal" | Registered in `rez-next-config/src/keys.rs` as a **deprecated** `KeyType::Bool` and listed in `_deprecated_settings`; **not** in `config_schema` | Registered on the Rust side but not schema-validated. This is a genuine schema-coverage gap, recorded rather than hidden. Closing it is a separate change requiring an explicit decision. |
| `plugins` | `plugins = {}` — namespace for `plugins.<plugin>.<setting>` settings | Registered in `keys.rs` as `KeyType::Dict` with an explicit comment that plugin settings are addressed as dotted paths "rather than as ordinary scalar keys, so they are registered but not schema-validated as a single value"; `config.py` handles `plugins` separately (`_PluginConfigs`, `__getattr__`, completions) | Namespace container, not a flat scalar. Deliberately outside `config_schema`; adding a flat `plugins` entry would be wrong. |

## Why the strict invariant stays open

The issue's acceptance criterion is two empty diffs. Honestly satisfying it
would require either adding five deprecated rez-1 keys and a dotted-plugin
container to `config_schema` (a product/compatibility decision beyond this
task's P3 follow-up scope), or deleting keys / reusing one source for both
sides (a fake pass, explicitly forbidden). Neither is done here. The
divergence is pinned to exactly these six keys with a documented policy, and
any change in either direction is detected by the tests.

To re-run:

```bash
python -I verification/pip4717_config_p3/run_real_keyset_comparison.py
python -m unittest discover -s verification/pip4717_config_p3 -v
```
