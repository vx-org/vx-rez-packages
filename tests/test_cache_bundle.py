"""A cache hit must remain verified and never contact the network offline."""

import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.cache_bundle import CacheError, _checked_download, _relative


class DownloadCacheTests(unittest.TestCase):
    def test_online_download_then_offline_hit_rechecks_bytes(self):
        payload = b"a verified release artifact"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / digest
            with patch("tools.cache_bundle.urlopen", return_value=io.BytesIO(payload)):
                _checked_download("https://example.org/artifact", digest, path, offline=False)
            with patch("tools.cache_bundle.urlopen", side_effect=AssertionError("network used")):
                self.assertEqual(
                    _checked_download("https://example.org/artifact", digest, path, offline=True),
                    path,
                )
                path.write_bytes(b"corrupted cache")
                with self.assertRaisesRegex(CacheError, "cached checksum mismatch"):
                    _checked_download("https://example.org/artifact", digest, path, offline=True)

    def test_bad_download_never_enters_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "artifact"
            with (
                patch("tools.cache_bundle.urlopen", return_value=io.BytesIO(b"wrong bytes")),
                self.assertRaisesRegex(CacheError, "download checksum mismatch"),
            ):
                _checked_download("https://example.org/artifact", "a" * 64, path, offline=False)
            self.assertFalse(path.exists())
            self.assertEqual(list(path.parent.iterdir()), [])

    def test_offline_miss_does_not_contact_network(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("tools.cache_bundle.urlopen", side_effect=AssertionError("network used")),
            self.assertRaisesRegex(CacheError, "offline cache miss"),
        ):
            _checked_download(
                "https://example.org/artifact",
                "a" * 64,
                Path(temporary) / "missing",
                offline=True,
            )

    def test_repository_paths_reject_cross_platform_escapes(self):
        for name in ("../escape", "/absolute", "C:/drive", "a\\b", "a/../escape", "file:stream"):
            with self.subTest(name=name), self.assertRaises(CacheError):
                _relative(name)


if __name__ == "__main__":
    unittest.main()
