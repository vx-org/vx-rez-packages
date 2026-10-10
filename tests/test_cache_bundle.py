"""A cache hit must remain verified and never contact the network offline."""

import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.cache_bundle import CacheError, _checked_download, _relative, _verify_repository


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
        for name in (
            "../escape",
            "/absolute",
            "C:/drive",
            "a\\b",
            "a/../escape",
            "file:stream",
            "a//b",
            "a/./b",
            "a/b/",
            "a/\x00b",
        ):
            with self.subTest(name=name), self.assertRaises(CacheError):
                _relative(name)


class VariantRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repository = Path(self.temporary.name).resolve()
        self.package = self.repository / "fixture/1.2.3"
        self.payload = self.package / "platform-windows/arch-x86_64/payload"
        self.payload.mkdir(parents=True)
        (self.payload / "fixture.exe").write_bytes(b"actual payload")
        (self.package / "package.py").write_bytes(b"name = 'fixture'\nversion = '1.2.3'\n")
        self.selected = {
            "tool": "fixture",
            "version": "1.2.3",
            "platform": "windows",
            "arch": "x86_64",
            "triple": "x86_64-pc-windows-msvc",
            "asset_name": "fixture-1.2.3-x86_64-pc-windows-msvc.rez.tar.zst",
            "package_root": "fixture/1.2.3",
        }
        self.manifest = {
            "schema_version": 1,
            **self.selected,
            "payload_root": "fixture/1.2.3/platform-windows/arch-x86_64/payload",
            "upstream": {
                "manifest_url": "https://example.invalid/SHA256SUMS",
                "archive_url": "https://example.invalid/fixture",
                "archive_sha256": "a" * 64,
            },
            "checksums": {
                "algorithm": "sha256",
                "file": "fixture/1.2.3/sha256sums.txt",
                "scope": "all regular files except sha256sums.txt",
            },
            "compatibility": {"rez_next": ">=0", "vx_rez_adapter": ">=0"},
        }
        self.write_checksums()

    def write_checksums(self):
        (self.package / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        lines = []
        for file in sorted(self.repository.rglob("*")):
            if file.is_file() and file.name != "sha256sums.txt":
                digest = hashlib.sha256(file.read_bytes()).hexdigest()
                lines.append(f"{digest}  {file.relative_to(self.repository).as_posix()}")
        (self.package / "sha256sums.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_nested_variant_payload_is_verified_and_corruption_is_detected(self):
        _verify_repository(self.repository, self.selected)
        (self.payload / "fixture.exe").write_bytes(b"corrupt native executable")
        with self.assertRaisesRegex(CacheError, "checksum mismatch"):
            _verify_repository(self.repository, self.selected)

    def test_manifest_cannot_redirect_payload_to_another_package_or_missing_root(self):
        for root in ("other/1.2.3/payload", "fixture/1.2.3/absent/payload"):
            with self.subTest(root=root):
                self.manifest["payload_root"] = root
                self.write_checksums()
                with self.assertRaisesRegex(CacheError, "inside its package|missing"):
                    _verify_repository(self.repository, self.selected)

    def test_payload_directory_alias_is_rejected_on_cache_reverification(self):
        actual = self.payload.with_name("actual-payload")
        self.payload.rename(actual)
        try:
            self.payload.symlink_to(actual.name, target_is_directory=True)
        except OSError:
            self.skipTest("native symlink creation is unavailable")
        with self.assertRaisesRegex(CacheError, "payload root contains a link"):
            _verify_repository(self.repository, self.selected)


if __name__ == "__main__":
    unittest.main()
