"""Named regression tests for the four config override error branches (PIP-4717 A).

Every test uses only synthetic in-memory values. These lock the contracts of the
four review findings A1-A4 against the synthetic port in ``config_override.py``;
they do not execute the Rust crate.
"""

from __future__ import annotations

import dataclasses
import io
import unittest
from contextlib import redirect_stderr

import config_override as co


class TestAssignCache(unittest.TestCase):
    def test_unknown_cache_subkey_is_rejected(self):
        target = co.CacheConfig(memory_cache_size=500, enable_disk_cache=False)
        with self.assertRaisesRegex(co.ConfigOverrideError, "unknown cache key 'typo'"):
            co.assign_cache(target, {"typo": 1})
        self.assertEqual(target.memory_cache_size, 500)
        self.assertFalse(target.enable_disk_cache)

    def test_cache_non_object_is_rejected_and_target_unchanged(self):
        target = co.CacheConfig(memory_cache_size=500, enable_disk_cache=False)
        with self.assertRaisesRegex(co.ConfigOverrideError, "invalid cache override"):
            co.assign_cache(target, 7)
        self.assertEqual(target.memory_cache_size, 500)
        self.assertFalse(target.enable_disk_cache)

    def test_partial_cache_patch_keeps_sibling_keys(self):
        # Control only: the already-fixed P2 behaviour (config.rs:1102) still
        # holds. Not new coverage of the P3 findings.
        target = co.CacheConfig(memory_cache_size=500, enable_disk_cache=False)
        co.assign_cache(target, {"memory_cache_size": 999})
        self.assertEqual(target.memory_cache_size, 999)
        self.assertFalse(target.enable_disk_cache)


class TestAssignPathList(unittest.TestCase):
    def test_path_list_non_string_item_is_rejected(self):
        target = ["/keep"]
        with self.assertRaisesRegex(co.ConfigOverrideError, "expected every path entry"):
            co.assign_path_list(target, ["ok", 7])
        self.assertEqual(target, ["/keep"])

    def test_path_list_non_array_non_string_is_rejected(self):
        target = ["/keep"]
        with self.assertRaisesRegex(co.ConfigOverrideError, "expected a path list, got mapping"):
            co.assign_path_list(target, {"a": 1})
        self.assertEqual(target, ["/keep"])


class TestCacheKeyDerivation(unittest.TestCase):
    def test_cache_key_message_tracks_struct_fields(self):
        @dataclasses.dataclass
        class ExtendedConfig(co.CacheConfig):
            extra_cache_key: int = 0

        target = ExtendedConfig()
        with self.assertRaisesRegex(co.ConfigOverrideError, "extra_cache_key") as ctx:
            co.assign_cache(target, {"typo": 1})
        self.assertIn("unknown cache key 'typo'", str(ctx.exception))


class TestReportComment(unittest.TestCase):
    def test_report_comment_does_not_claim_rez_equivalence(self):
        comment = co.REPORT_BEHAVIOR_COMMENT
        self.assertIn("reported instead of failing hard", comment)
        self.assertNotIn("matching rez's `ConfigurationError`", comment)
        self.assertIn("NOT equivalent", comment)

    def test_report_goes_to_stderr_and_loader_continues(self):
        stream = io.StringIO()
        with redirect_stderr(stream):
            co.apply_env_overrides_and_report(["bad REZ_CACHE_JSON"])
        self.assertIn("rez-next: ignoring bad REZ_CACHE_JSON", stream.getvalue())


class TestEnvLock(unittest.TestCase):
    def test_load_returns_config_holds_env_lock(self):
        # A4: test_load_returns_config must hold env_lock() around load().
        with self.assertRaisesRegex(co.ConfigOverrideError, "env_lock"):
            co.load()
        with co.env_lock():
            cfg = co.load()
        self.assertTrue(cfg["version"])
