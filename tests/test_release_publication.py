from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.build_bundle import BundleError
from tools.verify_release import verify_release


class ReleasePublicationTests(unittest.TestCase):
    def test_draft_assets_must_have_identical_names_and_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected, downloaded = root / "expected", root / "downloaded"
            expected.mkdir()
            downloaded.mkdir()
            for directory in (expected, downloaded):
                (directory / "runtime.rez.tar.zst").write_bytes(b"real release bytes")
                (directory / "index.json").write_bytes(b"index bytes")
            verify_release(expected, downloaded)
            (downloaded / "runtime.rez.tar.zst").write_bytes(b"tampered remote bytes")
            with self.assertRaisesRegex(BundleError, "checksum mismatch"):
                verify_release(expected, downloaded)
            (downloaded / "runtime.rez.tar.zst").unlink()
            with self.assertRaisesRegex(BundleError, "asset names differ"):
                verify_release(expected, downloaded)

    def test_empty_draft_cannot_be_published(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            self.assertRaisesRegex(BundleError, "asset names differ"),
        ):
            verify_release(Path(temporary), Path(temporary))
