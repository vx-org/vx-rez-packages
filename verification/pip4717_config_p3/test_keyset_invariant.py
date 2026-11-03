"""Synthetic-fixture tests for the keyset comparator (PIP-4717 B).

The real bidirectional comparison against rez 3.4.0 is NOT executed here: the
independent reference key list is unavailable (see ``MISSING_EVIDENCE``). These
tests only prove the comparator itself detects drift in both directions, using
synthetic key sets. A green result here does NOT mean the keyset invariant passed.
"""

from __future__ import annotations

import unittest

import keyset_invariant as ki


class TestComparator(unittest.TestCase):
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


class TestRealBidirectionalInvariant(unittest.TestCase):
    @unittest.skipUnless(
        ki.load_keys(ki.SCHEMA_SOURCE_ENV) is not None
        and ki.load_keys(ki.REFERENCE_SOURCE_ENV) is not None,
        "UNVERIFIED (not passed): " + ki.MISSING_EVIDENCE,
    )
    def test_bidirectional_keyset_equality(self):
        schema = ki.load_keys(ki.SCHEMA_SOURCE_ENV)
        reference = ki.load_keys(ki.REFERENCE_SOURCE_ENV)
        diff = ki.compare_keysets(schema, reference)
        self.assertEqual(diff["missing_in_schema"], [], "upstream keys missing from schema")
        self.assertEqual(diff["missing_in_reference"], [], "schema keys missing upstream")
