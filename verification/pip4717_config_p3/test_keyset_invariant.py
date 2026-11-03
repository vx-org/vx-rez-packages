"""Bidirectional keyset tests (PIP-4717 B).

The real comparison IS executed against two vendored, independently sourced
files: upstream rez 3.4.0 ``rezconfig.py`` and rez-next ``config_schema``.
It currently FAILS strict equality with six documented upstream keys absent
from the schema. This is recorded rather than skipped, waived or faked.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import keyset_invariant as ki


class TestComparator(unittest.TestCase):
    """Synthetic drift-detection tests for the comparator itself (retained)."""

    def test_comparator_detects_missing_in_schema(self):
        diff = ki.compare_keysets(["a", "b"], ["a", "b", "c"])
        self.assertEqual(diff["missing_in_schema"], ["c"])
        self.assertEqual(diff["missing_in_reference"], [])

    def test_comparator_detects_missing_in_reference(self):
        diff = ki.compare_keysets(["a", "b", "c"], ["a", "b"])
        self.assertEqual(diff["missing_in_schema"], [])
        self.assertEqual(diff["missing_in_reference"], ["c"])

    def test_comparator_empty_diff_for_equal_keysets(self):
        diff = ki.compare_keysets(["a", "b"], ["b", "a"])
        self.assertEqual(diff, {"missing_in_schema": [], "missing_in_reference": []})

    def test_keysets_equal_detects_registry_addition(self):
        registry = ["debug_build", "debug_resolve"]
        schema = ["debug_build", "debug_resolve"]
        self.assertTrue(ki.keysets_equal(registry, schema))
        registry.append("newly_added_key")  # added without schema registration
        self.assertFalse(ki.keysets_equal(registry, schema))


class TestSourceIndependence(unittest.TestCase):
    """Negative cases: a same-source or same-side input must not fake a pass."""

    def test_real_sources_are_independent(self):
        sources = ki.load_real_key_sources()
        self.assertNotEqual(sources.schema_path.resolve(), sources.reference_path.resolve())
        self.assertNotEqual(sources.schema_path.read_bytes(), sources.reference_path.read_bytes())

    def test_same_file_env_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.json"
            path.write_text('["a", "b"]', encoding="utf-8")
            env = {
                ki.SCHEMA_SOURCE_ENV: str(path),
                ki.REFERENCE_SOURCE_ENV: str(path),
            }
            # Without the independence check this would be an empty diff and a
            # green test. It must be rejected instead.
            with (
                mock.patch.dict(os.environ, env, clear=False),
                self.assertRaises(ki.SourceIndependenceError),
            ):
                ki.load_keys_from_env()

    def test_identical_content_distinct_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a.json"
            b = Path(tmp) / "b.json"
            a.write_text('["a", "b"]', encoding="utf-8")
            b.write_text('["a", "b"]', encoding="utf-8")
            with self.assertRaises(ki.SourceIndependenceError):
                ki.assert_distinct_sources(a, b)

    def test_rez_next_own_rezconfig_is_rejected_as_reference(self):
        # rez-next's compatibility/defaults module is the SAME side as
        # config_schema; using it as the reference would be circular.
        with self.assertRaises(ki.SourceIndependenceError):
            ki.assert_independent_sources(ki.SCHEMA_SOURCE, ki.SAME_SIDE_REZCONFIG)

    def test_schema_and_reference_trees_cannot_be_swapped(self):
        with self.assertRaises(ki.SourceIndependenceError):
            ki.assert_independent_sources(ki.REFERENCE_SOURCE, ki.SCHEMA_SOURCE)

    def test_same_source_would_otherwise_fake_an_empty_diff(self):
        # Document the exact failure mode the independence guard prevents.
        schema = ["a", "b"]
        self.assertEqual(
            ki.compare_keysets(schema, list(schema)),
            {"missing_in_schema": [], "missing_in_reference": []},
        )


class TestVendoredSourcesAreUnmodified(unittest.TestCase):
    """Pin both source hashes: no key was deleted or injected to force a pass."""

    def _assert_forms_pinned(self, path: Path, lf_pin: str, crlf_pin: str) -> None:
        normalized = ki.normalize_line_endings(path.read_bytes())
        # Primary pin: EOL-normalized (LF) digest, independent of checkout EOL.
        self.assertEqual(ki.source_sha256(path), lf_pin)
        self.assertEqual(hashlib.sha256(normalized).hexdigest(), lf_pin)
        # Second pinned convention: the CRLF-rendered digest from the first delivery.
        self.assertEqual(hashlib.sha256(ki.crlf_line_endings(normalized)).hexdigest(), crlf_pin)
        # Platform proof: a CRLF copy normalizes back to the same primary pin.
        with tempfile.TemporaryDirectory() as tmp:
            crlf_copy = Path(tmp) / "source.py"
            crlf_copy.write_bytes(ki.crlf_line_endings(normalized))
            self.assertEqual(ki.source_sha256(crlf_copy), lf_pin)

    def test_reference_source_hash_is_pinned(self):
        self._assert_forms_pinned(
            ki.REFERENCE_SOURCE, ki.REFERENCE_SOURCE_SHA256, ki.REFERENCE_SOURCE_CRLF_SHA256
        )

    def test_schema_source_hash_is_pinned(self):
        self._assert_forms_pinned(
            ki.SCHEMA_SOURCE, ki.SCHEMA_SOURCE_SHA256, ki.SCHEMA_SOURCE_CRLF_SHA256
        )

    def test_no_keys_were_deleted_from_either_source(self):
        sources = ki.load_real_key_sources()
        self.assertEqual(len(sources.reference_keys), 146)
        self.assertEqual(len(sources.schema_keys), 140)
        for key in ki.KNOWN_DIVERGENCE:
            self.assertIn(key, sources.reference_keys)
            self.assertNotIn(key, sources.schema_keys)


class TestRealBidirectionalComparison(unittest.TestCase):
    """The real comparison, executed and honestly reported as FAILING."""

    def test_real_comparison_documents_the_six_key_divergence(self):
        sources = ki.load_real_key_sources()
        diff = ki.compare_keysets(sources.schema_keys, sources.reference_keys)
        self.assertEqual(diff["missing_in_reference"], [])
        self.assertEqual(diff["missing_in_schema"], list(ki.KNOWN_DIVERGENCE))
        self.assertFalse(
            ki.keysets_equal(sources.schema_keys, sources.reference_keys),
            "strict keyset equality is NOT satisfied; do not report B as passed",
        )

    def test_new_upstream_key_without_schema_registration_is_detected(self):
        # Simulates a key added to the authoritative set without being
        # registered in config_schema: the pinned divergence test must go red.
        sources = ki.load_real_key_sources()
        reference = [*sources.reference_keys, "brand_new_registry_key"]
        diff = ki.compare_keysets(sources.schema_keys, reference)
        self.assertIn("brand_new_registry_key", diff["missing_in_schema"])
        self.assertFalse(ki.keysets_equal(sources.schema_keys, reference))
        self.assertNotEqual(diff["missing_in_schema"], list(ki.KNOWN_DIVERGENCE))

    def test_new_schema_key_without_upstream_key_is_detected(self):
        sources = ki.load_real_key_sources()
        schema = [*sources.schema_keys, "rez_next_only_key"]
        diff = ki.compare_keysets(schema, sources.reference_keys)
        self.assertEqual(diff["missing_in_reference"], ["rez_next_only_key"])

    @unittest.expectedFailure
    def test_strict_bidirectional_keyset_equality(self):
        # The acceptance criterion is two empty diffs. It is NOT met today.
        # This is an EXPECTED FAILURE, not a skip and not a pass: deleting the
        # six keys or feeding the same source to both sides would turn it into
        # an UNEXPECTED SUCCESS, which unittest reports as a failing result.
        sources = ki.load_real_key_sources()
        diff = ki.compare_keysets(sources.schema_keys, sources.reference_keys)
        self.assertEqual(diff["missing_in_schema"], [], "upstream keys missing from schema")
        self.assertEqual(diff["missing_in_reference"], [], "schema keys missing upstream")
