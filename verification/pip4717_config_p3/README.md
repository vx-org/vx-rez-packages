# PIP-4717 config follow-up: real production fix + honest keyset comparison

Isolated task directory for the four P3 findings carried over from rez-next
#378 and the bidirectional keyset invariant (PIP-4717 A + B). This is the
NACK-fix continuation of `2647505`: the first delivery substituted a Python
port for the real Rust implementation and reported B as `UNVERIFIED`. Both are
corrected here.

## What changed from the first delivery

- **A is now landed in the real Rust source.** `crates/rez-next-common/src/
  config.rs` is a verbatim copy of the production file at rez-next head
  `240500672ec42c916aab35a8ae3a638c6e2d4302` (#380 merged head) with **only** the
  four P3 source fixes applied. `upstream/rez-next@2405006/.../config.rs` holds
  the unmodified pristine copy; `config_p3_fix.patch` is the unified diff with
  the real repo-relative paths and can be applied directly to a rez-next
  checkout. `tools/build_fixed_config.py` reproduces the transformation with
  one-match assertions on every anchor.
- **The Rust source is compiled and tested for real.** `rust_probe/` is a small
  standalone Cargo crate that compiles the fixed `config.rs` via `#[path]`,
  supplying verbatim copies of the only crate-internal items it references
  (`error.rs`, `project.rs`, `keys.rs`). `cargo test --offline` runs the full
  production test suite plus the new A regression tests against that real file.
  It is not a synthetic model.
- **B is executed, not skipped.** Two independent authoritative sources are
  vendored read-only and AST-compared. The real bidirectional comparison
  genuinely FAILs with six documented keys. See `KEYSET_COMPATIBILITY.md`.

The earlier "synthetic fixtures only" constraint limited test *data* and
isolated *copies*; it never authorised replacing the production implementation
with a Python port. `config_override.py` and its tests are retained as a
secondary cross-check only, not as acceptance evidence.

## Source provenance

| File | Origin | SHA-256 prefix (LF-normalized) |
| --- | --- | --- |
| `upstream/rez-next@2405006/crates/rez-next-common/src/config.rs` | rez-next `2405006` | `99cfd07cc5dd` |
| `upstream/rez-next@2405006/crates/rez-next-python/python/rez_next/config.py` | rez-next `2405006` | `eb812d59fed0` |
| `upstream/rez-3.4.0/src/rez/rezconfig.py` | upstream rez 3.4.0 | `0bf79731e179` |

The repo commits these blobs with LF (`.gitattributes`: `* text=auto
eol=lf`). The first delivery pinned the CRLF-rendered digests, so both
source-hash tests failed on a normal checkout. `keyset_invariant.py` now
hashes EOL-normalized bytes (the LF form above) as the primary pin and keeps
the CRLF-rendered digest as a second pin, so both conventions are explicit and
the check is platform-independent.

The rez-next `origin/main` (`7dd9410`) copy of `config.rs` is unchanged since
the #380 head, so all four P3 items were still open; nothing already merged was
repeated. No other task's checkout was modified — all rez-next worktrees in
this workspace belong to other tasks, so this delivery stays in its own
isolated directory on `agent/agent/pip-4717`.

## A: named regression tests in the real Rust file

| Finding | Branch / behaviour | Named Rust test |
| --- | --- | --- |
| A1-a | `assign_cache` rejects unknown subkey, target unchanged | `test_assign_cache_rejects_unknown_subkey_and_preserves_target` |
| A1-b | `assign_cache` rejects non-object, target unchanged | `test_assign_cache_rejects_non_object_and_preserves_target` |
| A1-c | `assign_path_list` rejects non-string array item | `test_assign_path_list_rejects_non_string_item_and_preserves_target` |
| A1-d | `assign_path_list` rejects non-array / non-string | `test_assign_path_list_rejects_non_array_non_string_and_preserves_target` |
| A2 | stderr-report comment no longer claims rez equivalence | `test_report_comment_does_not_claim_rez_equivalence` |
| A3 | accepted-cache-key wording derived from the struct | `test_expected_cache_keys_is_derived_from_serialized_struct`, `test_unknown_cache_key_message_lists_derived_keys` |
| A4 | `test_load_returns_config` holds `env_lock()` | `test_load_returns_config_holds_env_lock` |
| control | already-fixed partial patch keeps sibling keys | `test_assign_cache_partial_patch_keeps_sibling_keys` |

A2 and A4 are source-text properties, so their tests read the real
`config.rs` back with `include_str!`. Search needles are split with `concat!`
so a test cannot satisfy itself by matching its own literal. A3's derivation
test feeds a simulated extra struct field through `expected_cache_keys()` and
asserts it appears in the wording — reverting to the hardcoded `CACHE_KEYS`
constant makes that test red.

`rust_mutation_checks.py` reverts each A fix in a private copy of the real
Rust source, recompiles with `cargo test --offline`, and requires the exact
named test to run and fail while the unmutated baseline passes.

## B: executed comparison, honest FAIL

`keyset_invariant.py` AST-extracts 146 upstream keys and 140 `config_schema`
keys from two independent vendored trees. The real comparison produces
`missing_in_schema` = 6 keys and `missing_in_reference` = empty;
`keysets_equal()` is `False`. `KEYSET_COMPATIBILITY.md` records the per-key
compatibility policy. Nothing is deleted, no source is reused, and both source
hashes are pinned in LF- and CRLF-normalized forms. Source-independence
negative cases (same file, identical content, same-side `rezconfig.py`,
swapped trees) are all covered.

## How to run

From the repository root:

```bash
# Real Rust production path (81 tests, offline)
cd verification/pip4717_config_p3/rust_probe
CARGO_TARGET_DIR=../.cargo-target cargo test --offline

# Executed real keyset comparison — exits 1 while strict equality is unmet
python -I verification/pip4717_config_p3/run_real_keyset_comparison.py

# Python harness (secondary cross-checks + B tests)
python -m unittest discover -s verification/pip4717_config_p3 -v

# Mutation verification (Python + real Rust)
python verification/pip4717_config_p3/mutation_checks.py
python verification/pip4717_config_p3/rust_mutation_checks.py
```

`cargo test` writes build artifacts to `.cargo-target/` (ignored via this
directory's `.gitignore`). All mutation runs happen in private temporary
copies; the task worktree is never modified.

The unified patch applies cleanly to a rez-next checkout with either
`git apply config_p3_fix.patch` or `patch -p1 < config_p3_fix.patch`; both
produce exactly `crates/rez-next-common/src/config.rs`. `tools/build_fixed_config.py`
regenerates that file byte-for-byte from the pristine snapshot.

## Validation results

| Check | Result |
| --- | --- |
| `cargo test --offline` (real Rust production source) | 81 passed, 0 failed |
| `python -I run_real_keyset_comparison.py` | exits **1**, 146 reference keys / 140 schema keys / 6 `missing_in_schema` / 0 `missing_in_reference` |
| `python -m unittest discover -s verification/pip4717_config_p3 -v` | 26 tests, OK (expected failures=1) |
| `python mutation_checks.py` | 25 baseline tests green, strict equality expected-failure, real comparison honest FAIL, 18/18 Python mutations killed |
| `python rust_mutation_checks.py` | full 81-test suite green, 9 named tests green, 8/8 real-Rust mutations killed and restored green |
| `python -m pytest -q tests` (repository suite) | 99 passed, 209 subtests passed |
| `ruff check` / `ruff format --check` (harness-owned Python) | clean |

The strict-equality `unittest.expectedFailure` is deliberate: deleting the six
keys or reusing one source for both sides would turn it into an *unexpected
success*, which unittest reports as a failure. Both sources are pinned over
LF-normalized bytes with the CRLF-rendered digest as a second convention (four
pins in total); each is checked by a hash test and has its own mutation in
`mutation_checks.py`, so key removal or injection is caught directly on any
checkout.
