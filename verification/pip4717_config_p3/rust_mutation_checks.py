"""Mutation verification against the REAL Rust production ``config.rs``.

Each mutation reverts one of the four PIP-4717 A fixes in a PRIVATE temporary
copy of ``crates/rez-next-common/src/config.rs``. The copy is then recompiled
by ``rust_probe`` (which includes that file through ``#[path]``) and the exact
named regression test is executed with ``cargo test --offline``. A mutation is
killed only when the test actually RAN and FAILED; a compile error, a filtered
-out test or a stale binary does not count. The unmutated baseline must pass,
and after every mutation the pristine source is restored and the same test must
go green again.

All runs share one case directory (a constant absolute path) so Cargo's
fingerprints detect each source edit and rebuild the probe crate. A shared
``CARGO_TARGET_DIR`` would otherwise reuse the baseline binary across copies.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parent
RUST_CONFIG = HARNESS_DIR / "crates" / "rez-next-common" / "src" / "config.rs"

TEST_PREFIX = "config::tests::"
EXPECTED_FULL_SUITE_PASSES = 81

RUST_TESTS = (
    "test_assign_cache_rejects_unknown_subkey_and_preserves_target",
    "test_assign_cache_rejects_non_object_and_preserves_target",
    "test_assign_cache_partial_patch_keeps_sibling_keys",
    "test_assign_path_list_rejects_non_string_item_and_preserves_target",
    "test_assign_path_list_rejects_non_array_non_string_and_preserves_target",
    "test_expected_cache_keys_is_derived_from_serialized_struct",
    "test_unknown_cache_key_message_lists_derived_keys",
    "test_report_comment_does_not_claim_rez_equivalence",
    "test_load_returns_config_holds_env_lock",
)


@dataclasses.dataclass(frozen=True)
class RustMutation:
    label: str
    old: str
    new: str
    test: str


MUTATIONS = (
    RustMutation(
        "A1-a unknown cache subkey guard removed",
        "                if !base.contains_key(key) {",
        "                if false {",
        "test_assign_cache_rejects_unknown_subkey_and_preserves_target",
    ),
    RustMutation(
        "A1-b non-object cache override accepted",
        "        other => merged = other.clone(),",
        "        other => {\n            let _ = other;\n        }",
        "test_assign_cache_rejects_non_object_and_preserves_target",
    ),
    RustMutation(
        "A1-c non-string path entry guard removed",
        "            if paths.len() != items.len() {",
        "            if false {",
        "test_assign_path_list_rejects_non_string_item_and_preserves_target",
    ),
    RustMutation(
        "A1-d non-array/non-string path value accepted",
        "        other => Err(format!(\n"
        '            "expected a path list, got {}",\n'
        "            value_kind_name(other)\n"
        "        )),",
        "        other => {\n"
        "            let _ = value_kind_name(other);\n"
        "            *target = Vec::new();\n"
        "            Ok(())\n"
        "        }",
        "test_assign_path_list_rejects_non_array_non_string_and_preserves_target",
    ),
    RustMutation(
        "A2 rez-equivalence over-claim restored",
        "    /// A malformed override is reported to stderr instead of failing hard:\n"
        "    /// upstream rez raises `ConfigurationError` and aborts\n"
        "    /// (`src/rez/config.py`), while rez-next keeps the previously loaded value\n"
        "    /// and continues. The stderr report is not equivalent to rez's behaviour.",
        "    /// A malformed override is a user-visible mistake and must not pass\n"
        "    /// silently: rez raises `ConfigurationError` for the same condition\n"
        "    /// (`src/rez/config.py`), and the config-file side of this loader already\n"
        "    /// errors rather than falling back to defaults.",
        "test_report_comment_does_not_claim_rez_equivalence",
    ),
    RustMutation(
        "A3 accepted-cache-key wording hardcoded again",
        '    keys.sort_unstable();\n    keys.join(", ")',
        '    keys.sort_unstable();\n    "hardcoded_cache_keys".to_string()',
        "test_expected_cache_keys_is_derived_from_serialized_struct",
    ),
    RustMutation(
        "A3 unknown-key message drops the derived wording",
        "                        \"unknown cache key '{key}'; expected one of {expected}\"",
        "                        \"unknown cache key '{key}'; expected one of hardcoded_keys\"",
        "test_unknown_cache_key_message_lists_derived_keys",
    ),
    RustMutation(
        "A4 env_lock guard removed from test_load_returns_config",
        "    fn test_load_returns_config() {\n"
        "        // Should not panic, even if no config file exists\n"
        "        let _guard = env_lock();",
        "    fn test_load_returns_config() {\n"
        "        // Should not panic, even if no config file exists",
        "test_load_returns_config_holds_env_lock",
    ),
)


def copy_case(dest: Path) -> tuple[Path, Path]:
    """Copy the probe crate and the real fixed config.rs into a private dir."""
    shutil.copytree(HARNESS_DIR / "rust_probe", dest / "rust_probe")
    shutil.copytree(HARNESS_DIR / "crates", dest / "crates")
    return dest / "rust_probe", dest / "crates" / "rez-next-common" / "src" / "config.rs"


def run_cargo(probe_dir: Path, cargo_target: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "CARGO_TARGET_DIR": str(cargo_target)}
    return subprocess.run(
        ["cargo", "test", "--offline", *args],
        cwd=probe_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def output_of(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


def full_suite_green(probe_dir: Path, cargo_target: Path) -> bool:
    output = output_of(run_cargo(probe_dir, cargo_target))
    return f"test result: ok. {EXPECTED_FULL_SUITE_PASSES} passed" in output


def named_test(probe_dir: Path, cargo_target: Path, test: str) -> str:
    return output_of(
        run_cargo(probe_dir, cargo_target, "--lib", "--", "--exact", TEST_PREFIX + test)
    )


def is_green(output: str, test: str) -> bool:
    return (
        "running 1 test" in output
        and f"test {TEST_PREFIX}{test} ... ok" in output
        and "test result: ok. 1 passed" in output
        and "test result: FAILED" not in output
    )


def is_red(output: str, test: str) -> bool:
    return (
        "running 1 test" in output
        and f"test {TEST_PREFIX}{test} ... FAILED" in output
        and "test result: FAILED. 0 passed; 1 failed" in output
    )


def main() -> int:
    print(f"rust config: {RUST_CONFIG}")
    ok = True

    with tempfile.TemporaryDirectory() as root_tmp:
        root = Path(root_tmp)
        cargo_target = root / "cargo-target"
        case = root / "case"
        case.mkdir()
        probe, config_path = copy_case(case)
        pristine = config_path.read_text(encoding="utf-8")

        print("\n[1/3] unmutated real Rust source: full production test suite")
        green = full_suite_green(probe, cargo_target)
        status = "GREEN" if green else "FAIL  "
        print(f"  {status}  cargo test --offline ({EXPECTED_FULL_SUITE_PASSES} tests)")
        ok = ok and green

        print("\n[2/3] unmutated real Rust source: each named regression test")
        for test in RUST_TESTS:
            passed = is_green(named_test(probe, cargo_target, test), test)
            print(f"  {'GREEN' if passed else 'FAIL  '}  {test}")
            ok = ok and passed

        print("\n[3/3] mutated real Rust source: red under mutation, green after restore")
        for mutation in MUTATIONS:
            count = pristine.count(mutation.old)
            if count != 1:
                print(f"  ANCHOR-ERROR ({count})  {mutation.label}")
                ok = False
                continue
            mutated = pristine.replace(mutation.old, mutation.new, 1)
            config_path.write_text(mutated, encoding="utf-8")
            killed = is_red(named_test(probe, cargo_target, mutation.test), mutation.test)
            config_path.write_text(pristine, encoding="utf-8")
            restored = is_green(named_test(probe, cargo_target, mutation.test), mutation.test)
            status = "KILLED  " if killed and restored else "SURVIVED"
            print(f"  {status}  {mutation.label} (red={killed}, restored-green={restored})")
            ok = ok and killed and restored

    print("\nRESULT:", "ALL RUST MUTATIONS KILLED" if ok else "INCOMPLETE / FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
