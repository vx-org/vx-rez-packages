# PIP-4717 config follow-up: bounded verification harness

Isolated task directory for the four P3 findings carried over from rez-next #378
and the missing bidirectional keyset invariant (PIP-4717 A + B).

## What this is (and is not)

This is a **self-contained synthetic harness**. The real implementation lives in
the `vx-org/rez-next` repository at
`crates/rez-next-common/src/config.rs` and is **not** copied, vendored or edited
here. This task's branch is `agent/agent/pip-4717` in `vx-rez-packages`; the
rez-next source exists only in sibling worktrees owned by other tasks. Touching
those would create a second writer and break the stage-3 (PIP-4612) / stage-4
serial order, so this delivery stays inside its own isolated directory.

`config_override.py` is a behaviour-faithful synthetic port of the two override
helpers. All test inputs are synthetic in-memory values; no real rezconfig file,
no downloaded rez 3.4.0 source, and no network data are used.

Before writing anything, the findings were re-checked against rez-next
`origin/main` (`7dd9410`): `crates/rez-next-common/src/config.rs` and
`crates/rez-next-config/src/keys.rs` are unchanged since the #380 head
(`2405006`), so all four P3 items and the keyset gap are still open — nothing
already fixed was repeated.

## Coverage locked by named tests

| Finding | Branch / behaviour | Named test |
| --- | --- | --- |
| A1-a | `assign_cache` rejects unknown subkey, target unchanged | `test_unknown_cache_subkey_is_rejected` |
| A1-b | `assign_cache` rejects non-object, target unchanged | `test_cache_non_object_is_rejected_and_target_unchanged` |
| A1-c | `assign_path_list` rejects non-string array item | `test_path_list_non_string_item_is_rejected` |
| A1-d | `assign_path_list` rejects non-array / non-string | `test_path_list_non_array_non_string_is_rejected` |
| A2 | stderr report wording does not claim rez equivalence | `test_report_comment_does_not_claim_rez_equivalence` |
| A2 | report goes to stderr, loader continues | `test_report_goes_to_stderr_and_loader_continues` |
| A3 | accepted-cache-key message derives from the struct | `test_cache_key_message_tracks_struct_fields` |
| A4 | `test_load_returns_config` holds `env_lock()` around `load()` | `test_load_returns_config_holds_env_lock` |
| B | comparator detects drift in both directions | `test_comparator_*`, `test_keysets_equal_detects_registry_addition` |
| — | control: already-fixed partial patch keeps sibling keys | `test_partial_cache_patch_keeps_sibling_keys` |

## Comment correction (A2), exact wording for upstream

Current text in `crates/rez-next-common/src/config.rs` (around line 527) still
claims equivalence with rez:

```rust
    /// A malformed override is a user-visible mistake and must not pass
    /// silently: rez raises `ConfigurationError` for the same condition
    /// (`src/rez/config.py`), and the config-file side of this loader already
    /// errors rather than falling back to defaults.
```

rez actually aborts on `Setting.validate`; rez-next warns and continues. Replace
with wording that states the divergence explicitly ("reported instead of failing
hard"):

```rust
    /// A malformed override is reported to stderr instead of failing hard:
    /// upstream rez raises `ConfigurationError` and aborts
    /// (`src/rez/config.py`), while rez-next keeps the previously loaded value
    /// and continues. The stderr report is not equivalent to rez's behaviour.
```

`config_override.py::REPORT_BEHAVIOR_COMMENT` carries the corrected wording and
is locked by a named test, so a regression back to the over-claim is caught.

## The keyset invariant is NOT passed

The real bidirectional comparison (`config_schema` keys == rez 3.4.0
`rezconfig.py` keys, both diffs empty, and failing when a registry key is added
without registration) is **not executed and must not be reported as passed**.
`test_bidirectional_keyset_equality` is explicitly skipped with the reason
`UNVERIFIED (not passed)`. The comparator itself is complete and its drift
detection is proven with synthetic key sets only. See `EVIDENCE_GAP.md`.

## How to run

From the repository root:

```bash
python -m unittest discover -s verification/pip4717_config_p3 -v
python verification/pip4717_config_p3/mutation_checks.py
```

`mutation_checks.py` copies the harness to a private temporary directory, applies
one mutation per named test, and runs that exact named test in a fresh
`python -m unittest <dotted.name>` subprocess. A mutation is killed only when the
named test actually runs and fails under mutation while the unmutated copy passes.
The task worktree is never modified.
