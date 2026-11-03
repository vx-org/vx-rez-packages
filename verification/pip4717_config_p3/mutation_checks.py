"""Execute named Python tests against mutated copies of the harness.

Each mutation is applied to a PRIVATE temporary copy of the harness; the named
unittest is then executed in a fresh interpreter (``python -m unittest
<dotted.name>``). A mutation counts as killed only when that exact test runs
and fails, while the unmutated copy of the same test passes. Nothing in the
task worktree is modified.

The authoritative A1-A4 mutation verification is in ``rust_mutation_checks.py``,
which mutates the REAL Rust ``config.rs`` and recompiles with ``cargo test``.
These Python mutations are a secondary cross-check of the harness itself.
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
HARNESS_FILES = (
    "config_override.py",
    "keyset_invariant.py",
    "test_config_override.py",
    "test_keyset_invariant.py",
    "run_real_keyset_comparison.py",
)

BASELINE_TESTS = (
    "test_config_override.TestAssignCache.test_unknown_cache_subkey_is_rejected",
    "test_config_override.TestAssignCache.test_cache_non_object_is_rejected_and_target_unchanged",
    "test_config_override.TestAssignCache.test_partial_cache_patch_keeps_sibling_keys",
    "test_config_override.TestAssignPathList.test_path_list_non_string_item_is_rejected",
    "test_config_override.TestAssignPathList.test_path_list_non_array_non_string_is_rejected",
    "test_config_override.TestCacheKeyDerivation.test_cache_key_message_tracks_struct_fields",
    "test_config_override.TestReportComment.test_report_comment_does_not_claim_rez_equivalence",
    "test_config_override.TestReportComment.test_report_goes_to_stderr_and_loader_continues",
    "test_config_override.TestEnvLock.test_load_returns_config_holds_env_lock",
    "test_keyset_invariant.TestComparator.test_comparator_detects_missing_in_schema",
    "test_keyset_invariant.TestComparator.test_comparator_detects_missing_in_reference",
    "test_keyset_invariant.TestComparator.test_comparator_empty_diff_for_equal_keysets",
    "test_keyset_invariant.TestComparator.test_keysets_equal_detects_registry_addition",
    "test_keyset_invariant.TestSourceIndependence.test_real_sources_are_independent",
    "test_keyset_invariant.TestSourceIndependence.test_same_file_env_input_is_rejected",
    "test_keyset_invariant.TestSourceIndependence.test_identical_content_distinct_files_are_rejected",
    "test_keyset_invariant.TestSourceIndependence.test_rez_next_own_rezconfig_is_rejected_as_reference",
    "test_keyset_invariant.TestSourceIndependence.test_schema_and_reference_trees_cannot_be_swapped",
    "test_keyset_invariant.TestSourceIndependence.test_same_source_would_otherwise_fake_an_empty_diff",
    "test_keyset_invariant.TestVendoredSourcesAreUnmodified.test_reference_source_hash_is_pinned",
    "test_keyset_invariant.TestVendoredSourcesAreUnmodified.test_schema_source_hash_is_pinned",
    "test_keyset_invariant.TestVendoredSourcesAreUnmodified.test_no_keys_were_deleted_from_either_source",
    "test_keyset_invariant.TestRealBidirectionalComparison.test_real_comparison_documents_the_six_key_divergence",
    "test_keyset_invariant.TestRealBidirectionalComparison.test_new_upstream_key_without_schema_registration_is_detected",
    "test_keyset_invariant.TestRealBidirectionalComparison.test_new_schema_key_without_upstream_key_is_detected",
)

# The strict invariant genuinely fails: unittest must report exactly one
# expected failure, never a pass or a skip.
STRICT_EQUALITY_TEST = (
    "test_keyset_invariant.TestRealBidirectionalComparison."
    "test_strict_bidirectional_keyset_equality"
)


@dataclasses.dataclass(frozen=True)
class Mutation:
    label: str
    target: str
    old: str
    new: str
    test: str


MUTATIONS = (
    Mutation(
        "A1-a unknown cache subkey",
        "config_override.py",
        "if key not in base:",
        "if False:",
        "test_config_override.TestAssignCache.test_unknown_cache_subkey_is_rejected",
    ),
    Mutation(
        "A1-b cache non-object",
        "config_override.py",
        "        merged = value",
        "        merged = dict(base)",
        "test_config_override.TestAssignCache.test_cache_non_object_is_rejected_and_target_unchanged",
    ),
    Mutation(
        "A1-c path list non-string item",
        "config_override.py",
        "if len(paths) != len(value):",
        "if False:",
        "test_config_override.TestAssignPathList.test_path_list_non_string_item_is_rejected",
    ),
    Mutation(
        "A1-d path list non-array/non-string",
        "config_override.py",
        '    raise ConfigOverrideError(f"expected a path list, got {value_kind_name(value)}")',
        "    target[:] = []",
        "test_config_override.TestAssignPathList.test_path_list_non_array_non_string_is_rejected",
    ),
    Mutation(
        "A2 comment over-claim restored",
        "config_override.py",
        "reported instead of failing hard",
        "matching rez's `ConfigurationError`",
        "test_config_override.TestReportComment.test_report_comment_does_not_claim_rez_equivalence",
    ),
    Mutation(
        "A2 stderr report moved to stdout",
        "config_override.py",
        "file=sys.stderr",
        "file=sys.stdout",
        "test_config_override.TestReportComment.test_report_goes_to_stderr_and_loader_continues",
    ),
    Mutation(
        "A3 cache keys hardcoded again",
        "config_override.py",
        'return ", ".join(base_keys)',
        'return ", ".join(_HARDCODED_CACHE_KEYS)',
        "test_config_override.TestCacheKeyDerivation.test_cache_key_message_tracks_struct_fields",
    ),
    Mutation(
        "A4 env_lock guard removed",
        "config_override.py",
        "if not _ENV_LOCK.locked():",
        "if False:",
        "test_config_override.TestEnvLock.test_load_returns_config_holds_env_lock",
    ),
    Mutation(
        "B missing_in_schema dropped",
        "keyset_invariant.py",
        '"missing_in_schema": sorted(reference - schema),',
        '"missing_in_schema": [],',
        "test_keyset_invariant.TestComparator.test_comparator_detects_missing_in_schema",
    ),
    Mutation(
        "B missing_in_reference dropped",
        "keyset_invariant.py",
        '"missing_in_reference": sorted(schema - reference),',
        '"missing_in_reference": [],',
        "test_keyset_invariant.TestComparator.test_comparator_detects_missing_in_reference",
    ),
    Mutation(
        "B equality short-circuited to True",
        "keyset_invariant.py",
        '    return not diff["missing_in_schema"] and not diff["missing_in_reference"]',
        "    return True",
        "test_keyset_invariant.TestComparator.test_keysets_equal_detects_registry_addition",
    ),
    Mutation(
        "B env-source independence check removed",
        "keyset_invariant.py",
        "    assert_distinct_sources(Path(schema_path), Path(reference_path))\n"
        "    schema = load_keys(SCHEMA_SOURCE_ENV)",
        "    pass  # independence check removed\n    schema = load_keys(SCHEMA_SOURCE_ENV)",
        "test_keyset_invariant.TestSourceIndependence.test_same_file_env_input_is_rejected",
    ),
    Mutation(
        "B upstream-tree independence check removed",
        "keyset_invariant.py",
        "    if not reference.is_relative_to(REFERENCE_TREE.resolve()):",
        "    if False and not reference.is_relative_to(REFERENCE_TREE.resolve()):",
        "test_keyset_invariant.TestSourceIndependence.test_rez_next_own_rezconfig_is_rejected_as_reference",
    ),
    Mutation(
        "B pinned divergence allowlist tampered",
        "keyset_invariant.py",
        '    "plugins",\n    "rez_1_environment_variables",',
        '    "rez_1_environment_variables",',
        "test_keyset_invariant.TestRealBidirectionalComparison.test_real_comparison_documents_the_six_key_divergence",
    ),
    Mutation(
        "B reference LF source hash pin tampered",
        "keyset_invariant.py",
        '"0bf79731e179ca0815b5364ffd810e23dbe7c974f2fd2aca78a0742b15778599"',
        '"0000000000000000000000000000000000000000000000000000000000000000"',
        "test_keyset_invariant.TestVendoredSourcesAreUnmodified.test_reference_source_hash_is_pinned",
    ),
    Mutation(
        "B schema LF source hash pin tampered",
        "keyset_invariant.py",
        '"eb812d59fed0f05d78862d6bc3f93cf58b1cd306708665f9304940fcbc23fb75"',
        '"0000000000000000000000000000000000000000000000000000000000000000"',
        "test_keyset_invariant.TestVendoredSourcesAreUnmodified.test_schema_source_hash_is_pinned",
    ),
    Mutation(
        "B reference CRLF source hash pin tampered",
        "keyset_invariant.py",
        '"c634be4d326be7cf41d1545e3b00b0495074281f0e9e09e384ac69b0ba852e05"',
        '"0000000000000000000000000000000000000000000000000000000000000000"',
        "test_keyset_invariant.TestVendoredSourcesAreUnmodified.test_reference_source_hash_is_pinned",
    ),
    Mutation(
        "B schema CRLF source hash pin tampered",
        "keyset_invariant.py",
        '"be12a3bd138cd021278d2ff48b45ea445a8fbc9da957da5a1abfc78f7c170c7b"',
        '"0000000000000000000000000000000000000000000000000000000000000000"',
        "test_keyset_invariant.TestVendoredSourcesAreUnmodified.test_schema_source_hash_is_pinned",
    ),
)


def copy_harness(dest: Path) -> None:
    """Copy the harness (including vendored independent sources) into scratch."""
    for name in HARNESS_FILES:
        shutil.copy2(HARNESS_DIR / name, dest / name)
    shutil.copytree(HARNESS_DIR / "upstream", dest / "upstream")


def run_named_test(workdir: Path, test: str) -> subprocess.CompletedProcess[str]:
    """Execute one exact dotted test name in a fresh interpreter."""
    env = {**os.environ, "PYTHONPATH": str(workdir)}
    return subprocess.run(
        [sys.executable, "-m", "unittest", "-v", test],
        cwd=workdir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


def baseline_passes(workdir: Path, test: str) -> bool:
    result = run_named_test(workdir, test)
    output = combined_output(result)
    return result.returncode == 0 and "Ran 1 test" in output and "OK" in output


def run_real_comparison(workdir: Path) -> subprocess.CompletedProcess[str]:
    """Run the standalone real comparison; it must exit 1 (strict FAIL)."""
    return subprocess.run(
        [sys.executable, "-I", str(workdir / "run_real_keyset_comparison.py")],
        cwd=workdir,
        capture_output=True,
        text=True,
        check=False,
    )


def mutation_killed(workdir: Path, test: str) -> bool:
    result = run_named_test(workdir, test)
    output = combined_output(result)
    ran = "Ran 1 test" in output
    failed = "FAILED" in output or "ERROR" in output
    return result.returncode != 0 and ran and failed


def main() -> int:
    print(f"harness: {HARNESS_DIR}")
    print(f"python:  {sys.executable}")
    ok = True

    print("\n[1/4] baseline: every named test must pass unmutated")
    with tempfile.TemporaryDirectory() as base_tmp:
        base_dir = Path(base_tmp)
        copy_harness(base_dir)
        for test in BASELINE_TESTS:
            passed = baseline_passes(base_dir, test)
            print(f"  {'GREEN' if passed else 'FAIL  '}  {test}")
            ok = ok and passed

    print("\n[2/4] strict equality: executed and reported as an expected failure")
    with tempfile.TemporaryDirectory() as strict_tmp:
        strict_dir = Path(strict_tmp)
        copy_harness(strict_dir)
        result = run_named_test(strict_dir, STRICT_EQUALITY_TEST)
        output = combined_output(result)
        expected_failure = (
            result.returncode == 0 and "Ran 1 test" in output and "expected failures=1" in output
        )
        print(
            f"  {'EXPECTED FAILURE' if expected_failure else 'UNEXPECTED'}  {STRICT_EQUALITY_TEST}"
        )
        ok = ok and expected_failure

    print("\n[3/4] real bidirectional comparison: must exit 1 with the six keys")
    with tempfile.TemporaryDirectory() as real_tmp:
        real_dir = Path(real_tmp)
        copy_harness(real_dir)
        result = run_real_comparison(real_dir)
        output = combined_output(result)
        honest_fail = (
            result.returncode == 1
            and "RESULT: FAIL" in output
            and all(
                key in output
                for key in (
                    "debug_old_commands",
                    "disable_rez_1_compatibility",
                    "error_old_commands",
                    "plugins",
                    "rez_1_environment_variables",
                    "warn_old_commands",
                )
            )
        )
        print(
            f"  {'FAIL (honest)' if honest_fail else 'UNEXPECTED'}  run_real_keyset_comparison.py"
        )
        ok = ok and honest_fail

    print("\n[4/4] mutation: each named test must go red under its mutation")
    for mutation in MUTATIONS:
        with tempfile.TemporaryDirectory() as mut_tmp:
            mut_dir = Path(mut_tmp)
            copy_harness(mut_dir)
            path = mut_dir / mutation.target
            text = path.read_text(encoding="utf-8")
            count = text.count(mutation.old)
            if count != 1:
                print(f"  ANCHOR-ERROR ({count})  {mutation.label}")
                ok = False
                continue
            path.write_text(text.replace(mutation.old, mutation.new, 1), encoding="utf-8")
            killed = mutation_killed(mut_dir, mutation.test)
            print(f"  {'KILLED  ' if killed else 'SURVIVED'}  {mutation.label}")
            ok = ok and killed

    print("\nRESULT:", "ALL MUTATIONS KILLED" if ok else "INCOMPLETE / FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
