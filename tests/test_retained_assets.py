"""Pinned originals remain byte-identical, bounded, and independently reusable."""

from __future__ import annotations

import hashlib
import io
import json
import ssl
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import Mock, patch

from tools.build_bundle import BundleError, load_definition
from tools.retain_release_assets import _HttpsRedirectHandler, retain_release_assets


def pin(name: str, payload: bytes) -> dict:
    return {
        "name": name,
        "url": "https://example.invalid/originals/archive",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size": len(payload),
    }


def recipe(assets: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "tool": "fixture",
        "version": "1.2.3",
        "release_date": "2026-10-04",
        "upstream_manifest": "https://example.invalid/SHA256SUMS",
        "compatibility": {"rez_next": ">=0.3.9", "vx_rez_adapter": ">=0.1.0"},
        "package": {
            "definition": {"source": "package.py", "sha256": "1" * 64},
            "description": "Retained archive fixture",
            "tools": ["fixture"],
            "path_entries": ["payload/bin"],
            "smoke_test": {"command": ["fixture", "--version"], "expect": "fixture"},
        },
        "provenance": {
            "repository": "https://example.invalid/fixture",
            "revision": "1" * 40,
            "license": "MIT",
            "source_url": "https://example.invalid/fixture-source.tar.gz",
            "source_sha256": "2" * 64,
        },
        "metadata": [{"source": "LICENSE", "destination": "LICENSE", "sha256": "3" * 64}],
        "targets": [
            {
                "triple": "x86_64-pc-windows-msvc",
                "platform": "windows",
                "arch": "x86_64",
                "runner": "windows-2025",
                "status": "supported",
                "upstream": {"url": "https://example.invalid/payload", "sha256": "4" * 64},
                "payload": {
                    "format": "binary",
                    "mappings": [{"source": ".", "destination": "bin/fixture.exe"}],
                },
            }
        ],
        "unsupported_targets": [],
        "release_assets": assets,
    }


class RetainedAssetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.output = self.root / "release"
        self.payload = b"an original upstream archive, never repacked\n"
        self.asset = pin("source.tar.xz", self.payload)
        self.definition = recipe([self.asset])

    def response(self, payload: bytes, url: str = "https://cdn.example.invalid/archive"):
        response = io.BytesIO(payload)
        response.url = url
        opener = Mock()
        opener.open.return_value = response
        return opener

    def test_schema_accepts_optional_pins_and_rejects_incomplete_assets(self) -> None:
        path = self.root / "recipe.json"
        for assets in (None, [], [self.asset]):
            definition = recipe(assets or [])
            if assets is None:
                del definition["release_assets"]
            path.write_text(json.dumps(definition), encoding="utf-8")
            self.assertEqual(load_definition(path), definition)
        for field in ("name", "url", "sha256", "size"):
            definition = recipe([{key: value for key, value in self.asset.items() if key != field}])
            path.write_text(json.dumps(definition), encoding="utf-8")
            with self.subTest(field=field), self.assertRaises(BundleError):
                load_definition(path)

    def test_verified_local_reuse_is_offline_and_manifest_is_deterministic(self) -> None:
        second_payload = b"another original"
        second = pin("another.zip", second_payload)
        (self.source / self.asset["name"]).write_bytes(self.payload)
        (self.source / second["name"]).write_bytes(second_payload)
        with patch(
            "tools.retain_release_assets.urllib.request.build_opener",
            side_effect=AssertionError("network must not be used"),
        ):
            first_manifest = retain_release_assets(
                recipe([self.asset, second]), self.output, source_directory=self.source
            )
            second_manifest = retain_release_assets(
                recipe([second, self.asset]), self.root / "second", source_directory=self.source
            )
            retain_release_assets(recipe([second, self.asset]), self.output)
        self.assertEqual(first_manifest.read_bytes(), second_manifest.read_bytes())
        manifest = json.loads(first_manifest.read_text(encoding="utf-8"))
        self.assertEqual(manifest, {"schema_version": 1, "assets": [second, self.asset]})
        self.assertNotIn(str(self.source), first_manifest.read_text(encoding="utf-8"))
        for asset, payload in ((self.asset, self.payload), (second, second_payload)):
            self.assertEqual((self.output / asset["name"]).read_bytes(), payload)
            self.assertEqual(
                (self.output / f"{asset['name']}.sha256").read_bytes(),
                f"{asset['sha256']}  {asset['name']}\n".encode(),
            )
        self.assertEqual(
            (self.output / "release-assets.json.sha256").read_text(encoding="utf-8"),
            f"{hashlib.sha256(first_manifest.read_bytes()).hexdigest()}  release-assets.json\n",
        )

    def test_download_rechecks_final_https_url_and_exact_bytes(self) -> None:
        opener = self.response(self.payload)
        with patch("tools.retain_release_assets.urllib.request.build_opener", return_value=opener):
            retain_release_assets(self.definition, self.output)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, self.asset["url"])
        self.assertEqual(opener.open.call_args.kwargs, {"timeout": 60})
        self.assertEqual((self.output / self.asset["name"]).read_bytes(), self.payload)

    def test_download_size_or_digest_failure_removes_only_its_partial_file(self) -> None:
        for payload, message in (
            (self.payload[:-1], "size mismatch"),
            (self.payload + b"extra", "exceeds pinned size"),
            (b"x" * len(self.payload), "checksum mismatch"),
        ):
            with self.subTest(message=message):
                self.output.mkdir(exist_ok=True)
                sentinel = self.output / "unrelated-existing-file"
                sentinel.write_bytes(b"preserved")
                opener = self.response(payload)
                with (
                    patch(
                        "tools.retain_release_assets.urllib.request.build_opener",
                        return_value=opener,
                    ),
                    self.assertRaisesRegex(BundleError, message),
                ):
                    retain_release_assets(self.definition, self.output)
                self.assertEqual(list(self.output.iterdir()), [sentinel])
                self.assertEqual(sentinel.read_bytes(), b"preserved")

    def test_bad_local_original_is_not_replaced_by_network_download(self) -> None:
        source = self.source / self.asset["name"]
        source.write_bytes(b"x" * len(self.payload))
        with (
            patch(
                "tools.retain_release_assets.urllib.request.build_opener",
                side_effect=AssertionError("network must not be used"),
            ),
            self.assertRaisesRegex(BundleError, "checksum mismatch"),
        ):
            retain_release_assets(self.definition, self.output, source_directory=self.source)
        self.assertEqual(list(self.output.iterdir()), [])
        self.assertEqual(source.read_bytes(), b"x" * len(self.payload))

    def test_existing_conflicting_asset_or_companion_fails_without_overwrite(self) -> None:
        self.output.mkdir()
        for name in (self.asset["name"], f"{self.asset['name']}.sha256", "release-assets.json"):
            with self.subTest(name=name):
                existing = self.output / name
                existing.write_bytes(b"previous release bytes")
                with (
                    patch(
                        "tools.retain_release_assets.urllib.request.build_opener",
                        side_effect=AssertionError("network must not be used"),
                    ),
                    self.assertRaises(BundleError),
                ):
                    retain_release_assets(self.definition, self.output)
                self.assertEqual(existing.read_bytes(), b"previous release bytes")
                self.assertEqual(list(self.output.iterdir()), [existing])
                existing.unlink()

    def test_existing_different_case_filename_is_a_portable_collision(self) -> None:
        self.output.mkdir()
        existing = self.output / "SOURCE.TAR.XZ"
        existing.write_bytes(self.payload)
        with self.assertRaisesRegex(BundleError, "existing portable name"):
            retain_release_assets(self.definition, self.output)
        self.assertEqual(list(self.output.iterdir()), [existing])

    def test_rejects_unsafe_reserved_duplicate_and_companion_asset_names(self) -> None:
        for name in (
            "../escape",
            "/absolute",
            "nested/archive",
            "nested\\archive",
            "C:drive",
            "name:stream",
            "trailing.",
            "trailing ",
            "CON",
            "COM¹.zip",
            "line\nbreak",
            "fixture.rez.tar.zst",
            "fixture.rez.tar.zst.sha256",
            "Index.JSON.sha256",
            "release-assets.json",
            "release-assets.json.sha256",
        ):
            with self.subTest(name=name), self.assertRaises(BundleError):
                retain_release_assets(recipe([pin(name, self.payload)]), self.output)
            self.assertFalse(self.output.exists())
        for names in (
            ("one.tar", "one.tar"),
            ("one.tar", "ONE.TAR"),
            ("one.tar", "one.tar.sha256"),
            ("café.tar", "cafe\u0301.tar"),
        ):
            with self.subTest(names=names), self.assertRaisesRegex(BundleError, "duplicate"):
                retain_release_assets(
                    recipe([pin(name, self.payload) for name in names]), self.output
                )
            self.assertFalse(self.output.exists())

    def test_rejects_non_https_credentials_fragments_and_unbounded_metadata(self) -> None:
        for url in (
            "http://example.invalid/archive",
            "https://user:password@example.invalid/archive",
            "https://example.invalid/archive#fragment",
            "https://example.invalid/archive#",
            "https:///archive",
            "https://example.invalid:bad/archive",
            "https://example.invalid/ar\nchive",
            "https://example.invalid\\archive",
        ):
            asset = {**self.asset, "url": url}
            with self.subTest(url=url), self.assertRaises(BundleError):
                retain_release_assets(recipe([asset]), self.output)
            self.assertFalse(self.output.exists())
        for size in (0, -1, True, 1.5):
            with self.subTest(size=size), self.assertRaises(BundleError):
                retain_release_assets(recipe([{**self.asset, "size": size}]), self.output)
            self.assertFalse(self.output.exists())

    def test_redirect_handler_refuses_http_or_credentials_before_following(self) -> None:
        handler = _HttpsRedirectHandler()
        request = urllib.request.Request(self.asset["url"])
        for url in (
            "http://cdn.example.invalid/archive",
            "https://secret@cdn.example.invalid/archive",
            "https://cdn.example.invalid/archive#fragment",
        ):
            with (
                self.subTest(url=url),
                patch.object(
                    urllib.request.HTTPRedirectHandler,
                    "redirect_request",
                    side_effect=AssertionError("unsafe redirect followed"),
                ),
                self.assertRaises(BundleError),
            ):
                handler.redirect_request(request, None, 302, "Found", {}, url)
        redirected = handler.redirect_request(
            request, None, 302, "Found", {}, "https://cdn.example.invalid/archive"
        )
        self.assertEqual(redirected.full_url, "https://cdn.example.invalid/archive")

    def test_non_https_final_response_is_rejected_without_reading_or_retaining(self) -> None:
        response = Mock()
        response.url = "http://cdn.example.invalid/archive"
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.side_effect = AssertionError("unsafe response read")
        opener = Mock()
        opener.open.return_value = response
        with (
            patch("tools.retain_release_assets.urllib.request.build_opener", return_value=opener),
            self.assertRaisesRegex(BundleError, "HTTPS"),
        ):
            retain_release_assets(self.definition, self.output)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_tls_failure_never_creates_a_retained_asset_or_checksum(self) -> None:
        opener = Mock()
        opener.open.side_effect = ssl.SSLError("certificate verification failed")
        with (
            patch("tools.retain_release_assets.urllib.request.build_opener", return_value=opener),
            self.assertRaisesRegex(ssl.SSLError, "certificate verification failed"),
        ):
            retain_release_assets(self.definition, self.output)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_atomic_install_race_cannot_overwrite_another_writers_asset(self) -> None:
        self.output.mkdir()
        destination = self.output / self.asset["name"]

        def concurrent_writer(temporary, final):
            self.assertEqual(final, destination)
            destination.write_bytes(b"another writer's asset")
            raise FileExistsError(final)

        with (
            patch(
                "tools.retain_release_assets.urllib.request.build_opener",
                return_value=self.response(self.payload),
            ),
            patch("tools.retain_release_assets.os.link", side_effect=concurrent_writer),
            self.assertRaisesRegex(BundleError, "size mismatch"),
        ):
            retain_release_assets(self.definition, self.output)
        self.assertEqual(destination.read_bytes(), b"another writer's asset")
        self.assertEqual(list(self.output.iterdir()), [destination])


if __name__ == "__main__":
    unittest.main()
