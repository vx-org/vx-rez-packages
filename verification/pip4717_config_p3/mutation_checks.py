"""Execute named tests against mutated copies of the synthetic fixture.

Each mutation is applied to a PRIVATE temporary copy of ``config_override.py`` /
``keyset_invariant.py``; the named unittest is then executed in a fresh subprocess
(``python -m unittest <dotted.name>``). A mutation counts as killed only when
that exact test runs and fails, while the unmutated copy of the same test passes.
Nothing in the task worktree is modified.
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
)

# Explicitly unverified: no independent rez 3.4.0 key list is available.
UNVERIFIED_TEST = (
    "test_keyset_invariant.TestRealBidirectionalInvariant.test_bidirectional_keyset_equality"
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
)


def copy_harness(dest: Path) -> None:
    """Copy the synthetic fixture into a private scratch directory."""
    for name in HARNESS_FILES:
        shutil.copy2(HARNESS_DIR / name, dest / name)


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

    print("\n[1/3] baseline: every named test must pass unmutated")
    with tempfile.TemporaryDirectory() as base_tmp:
        base_dir = Path(base_tmp)
        copy_harness(base_dir)
        for test in BASELINE_TESTS:
            passed = baseline_passes(base_dir, test)
            print(f"  {'GREEN' if passed else 'FAIL  '}  {test}")
            ok = ok and passed

    print("\n[2/3] unverified: real bidirectional keyset comparison")
    with tempfile.TemporaryDirectory() as skip_tmp:
        skip_dir = Path(skip_tmp)
        copy_harness(skip_dir)
        result = run_named_test(skip_dir, UNVERIFIED_TEST)
        output = combined_output(result)
        skipped = result.returncode == 0 and "skipped" in output
        print(f"  {'SKIPPED / UNVERIFIED' if skipped else 'UNEXPECTED'}  {UNVERIFIED_TEST}")
        ok = ok and skipped

    print("\n[3/3] mutation: each named test must go red under its mutation")
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
