"""A catalog delegates artifact verification and never interprets Rez requirements."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import zstandard

from tools.cache_bundle import CacheError
from tools.catalog import (
    CatalogError,
    generate_catalog,
    load_catalog,
    main,
    provision_from_catalog,
    validate_catalog,
    write_catalog,
)


def digest(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def release(tool: str = "fixture", version: str = "1.2.3") -> dict:
    return {
        "tool": tool,
        "version": version,
        "index_url": f"https://example.invalid/{tool}/{version}/index.json",
        "index_sha256": "a" * 64,
    }


def release_chain() -> dict:
    """Produce a real checksummed repository archive, index, and parent catalog."""
    root = "fixture/1.2.3"
    asset_name = "fixture-1.2.3-x86_64-pc-windows-msvc.rez.tar.zst"
    package = (
        b"name = 'fixture'\nversion = '1.2.3'\n"
        b"requires = ['platform-windows', 'arch-x86_64']\n"
        b"def commands():\n    env.PATH.prepend('{root}/payload/bin')\n"
    )
    selected = {
        "tool": "fixture",
        "version": "1.2.3",
        "platform": "windows",
        "arch": "x86_64",
        "triple": "x86_64-pc-windows-msvc",
        "asset_name": asset_name,
        "package_root": root,
    }
    manifest = {
        "schema_version": 1,
        **selected,
        "payload_root": f"{root}/payload",
        "upstream": {
            "manifest_url": "https://example.invalid/upstream/SHA256SUMS",
            "archive_url": "https://example.invalid/upstream/runtime.zip",
            "archive_sha256": "b" * 64,
        },
        "checksums": {
            "algorithm": "sha256",
            "file": f"{root}/sha256sums.txt",
            "scope": "all repository files except this checksum list",
        },
        "compatibility": {"rez_next": ">=0", "vx_rez_adapter": ">=0"},
    }
    files = {
        f"{root}/package.py": package,
        f"{root}/payload/bin/fixture.exe": b"fixture payload bytes",
        f"{root}/manifest.json": json.dumps(manifest).encode("utf-8"),
        "platform/windows/package.py": b"name = 'platform'\nversion = 'windows'\n",
        "arch/x86_64/package.py": b"name = 'arch'\nversion = 'x86_64'\n",
    }
    files[f"{root}/sha256sums.txt"] = "".join(
        f"{digest(contents)}  {name}\n" for name, contents in sorted(files.items())
    ).encode("utf-8")
    with io.BytesIO() as stream:
        with tarfile.open(fileobj=stream, mode="w") as archive:
            for name, contents in sorted(files.items()):
                member = tarfile.TarInfo(name)
                member.size = len(contents)
                member.mode = 0o755 if name.endswith(".exe") else 0o644
                archive.addfile(member, io.BytesIO(contents))
        bundle = zstandard.ZstdCompressor().compress(stream.getvalue())
    bundle_sha256 = digest(bundle)
    bundle_url = f"https://example.invalid/fixture/1.2.3/{asset_name}"
    index = json.dumps(
        {
            "schema_version": 1,
            "generated_at": "2026-10-09T00:00:00Z",
            "repository": "vx-org/fixture",
            "release_tag": "fixture-1.2.3",
            "bundles": [
                {
                    **selected,
                    "download_url": bundle_url,
                    "sha256": bundle_sha256,
                    "bundle_schema_version": 1,
                }
            ],
            "unsupported_targets": [],
        }
    ).encode("utf-8")
    entry = {**release(), "index_sha256": digest(index)}
    catalog = json.dumps(generate_catalog([entry])).encode("utf-8")
    catalog_url = "https://example.invalid/catalog.json"
    return {
        "catalog_url": catalog_url,
        "catalog_sha256": digest(catalog),
        "index_sha256": digest(index),
        "bundle_sha256": bundle_sha256,
        "package": package,
        "responses": {catalog_url: catalog, entry["index_url"]: index, bundle_url: bundle},
    }


class CatalogValidationTests(unittest.TestCase):
    def test_repeated_identity_rejected_even_when_pins_are_identical(self):
        for pin in ("a" * 64, "b" * 64):
            with self.subTest(pin=pin), self.assertRaisesRegex(CatalogError, "duplicate"):
                generate_catalog([release(), {**release(), "index_sha256": pin}])

    def test_invalid_release_urls_and_pins_are_rejected(self):
        cases = [
            {"index_url": value}
            for value in (
                "http://example.invalid/index.json",
                "https://",
                "https:///index.json",
                "https://user:password@example.invalid/index.json",
                "https://example.invalid/index.json#fragment",
                "https://example.invalid:invalid/index.json",
                "https://example.invalid/a b/index.json",
                "https://example.invalid/a\\b/index.json",
            )
        ] + [{"index_sha256": value} for value in ("a" * 63, "a" * 65, "A" * 64, "g" * 64)]
        for updates in cases:
            with self.subTest(updates=updates), self.assertRaises(CatalogError):
                generate_catalog([{**release(), **updates}])

    def test_catalog_rejects_unknown_contract_fields_and_empty_identities(self):
        cases = [
            {"schema_version": 2, "releases": [release()]},
            {"schema_version": 1, "releases": []},
            {"schema_version": 1, "releases": [release()], "latest": "fixture"},
            {"schema_version": 1, "releases": [{**release(), "tool": " "}]},
            {"schema_version": 1, "releases": [{**release(), "version": ""}]},
            {"schema_version": 1, "releases": [{**release(), "requires": ["python"]}]},
        ]
        for catalog in cases:
            with self.subTest(catalog=catalog), self.assertRaises(CatalogError):
                validate_catalog(catalog)

    def test_generation_is_deterministic_and_checksum_pins_written_bytes(self):
        entries = [release("zeta", "1.0"), release("alpha", "2.0"), release("alpha", "1.0")]
        original = json.dumps(entries)
        with tempfile.TemporaryDirectory() as temporary:
            first = Path(temporary) / "first" / "catalog.json"
            second = Path(temporary) / "second" / "catalog.json"
            write_catalog(generate_catalog(entries), first)
            write_catalog(generate_catalog(list(reversed(entries))), second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertNotIn(b"\r", first.read_bytes())
            self.assertEqual(
                first.with_name("catalog.json.sha256").read_bytes(),
                f"{digest(first.read_bytes())}  catalog.json\n".encode(),
            )
            self.assertEqual(
                [(item["tool"], item["version"]) for item in load_catalog(first)["releases"]],
                [("alpha", "1.0"), ("alpha", "2.0"), ("zeta", "1.0")],
            )
        self.assertEqual(json.dumps(entries), original)

    def test_ambiguous_json_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "ambiguous.json"
            source.write_text('{"schema_version": 1, "schema_version": 2, "releases": []}')
            with self.assertRaisesRegex(CatalogError, "duplicate catalog JSON key"):
                load_catalog(source)

    def test_cli_generates_and_validates_reviewed_local_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "reviewed.json"
            output = Path(temporary) / "dist" / "catalog.json"
            source.write_text(json.dumps(generate_catalog([release()])), encoding="utf-8")
            with (
                patch(
                    "sys.argv",
                    ["catalog", "generate", "--input", str(source), "--output", str(output)],
                ),
                patch("sys.stdout", new_callable=io.StringIO),
                patch("tools.cache_bundle.urlopen", side_effect=AssertionError("network used")),
            ):
                self.assertEqual(main(), 0)
            with patch("sys.argv", ["catalog", "validate", "--input", str(output)]):
                self.assertEqual(main(), 0)
            self.assertTrue(output.with_name("catalog.json.sha256").is_file())


class CatalogCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.cache = Path(temporary.name) / "cache"
        self.chain = release_chain()

    def provision(self, *, offline=False, tool="fixture", version="1.2.3"):
        return provision_from_catalog(
            self.chain["catalog_url"],
            self.chain["catalog_sha256"],
            self.cache,
            tool=tool,
            version=version,
            platform="windows",
            arch="x86_64",
            offline=offline,
        )

    def online(self):
        def download(url, **kwargs):
            return io.BytesIO(self.chain["responses"][url])

        with patch("tools.cache_bundle.urlopen", side_effect=download) as network:
            repository = self.provision()
        self.assertEqual(
            [call.args[0] for call in network.call_args_list], list(self.chain["responses"])
        )
        return repository

    def test_online_chain_then_offline_hit_preserves_actual_package_definition(self):
        repository = self.online()
        with patch("tools.cache_bundle.urlopen", side_effect=AssertionError("network used")):
            self.assertEqual(self.provision(offline=True), repository)
        self.assertEqual(
            (repository / "fixture/1.2.3/package.py").read_bytes(), self.chain["package"]
        )
        self.assertTrue((repository / "platform/windows/package.py").is_file())
        self.assertTrue((repository / "arch/x86_64/package.py").is_file())

    def test_offline_rechecks_catalog_index_archive_and_repository_corruption(self):
        repository = self.online()
        paths = (
            self.cache / "catalogs" / self.chain["catalog_sha256"],
            self.cache / "indexes" / self.chain["index_sha256"],
            self.cache / "archives" / self.chain["bundle_sha256"],
            repository / "fixture/1.2.3/package.py",
        )
        with patch("tools.cache_bundle.urlopen", side_effect=AssertionError("network used")):
            for path in paths:
                original = path.read_bytes()
                with self.subTest(path=path.name):
                    path.write_bytes(b"corrupted cache")
                    with self.assertRaisesRegex(CacheError, "checksum mismatch"):
                        self.provision(offline=True)
                    path.write_bytes(original)

    def test_exact_selection_never_interprets_requirement_or_alias(self):
        self.online()
        for tool, version in (("fixture", "1.2"), ("fixture", ">=1.2.3"), ("Fixture", "1.2.3")):
            with (
                self.subTest(tool=tool, version=version),
                patch("tools.cache_bundle.urlopen", side_effect=AssertionError("network used")),
                self.assertRaisesRegex(CatalogError, "expected exactly one catalog release"),
            ):
                self.provision(offline=True, tool=tool, version=version)

    def test_offline_misses_at_each_download_layer_never_use_network(self):
        self.online()
        paths = (
            self.cache / "catalogs" / self.chain["catalog_sha256"],
            self.cache / "indexes" / self.chain["index_sha256"],
            self.cache / "archives" / self.chain["bundle_sha256"],
        )
        for path in paths:
            original = path.read_bytes()
            with (
                self.subTest(path=path.parent.name),
                patch("tools.cache_bundle.urlopen", side_effect=AssertionError("network used")),
            ):
                path.unlink()
                with self.assertRaisesRegex(CacheError, "offline cache miss"):
                    self.provision(offline=True)
                path.write_bytes(original)

    def test_invalid_catalog_transport_pin_rejected_before_network(self):
        cases = (
            ("http://example.invalid/catalog.json", self.chain["catalog_sha256"]),
            (self.chain["catalog_url"], "a" * 63),
        )
        for url, pin in cases:
            with (
                self.subTest(url=url, pin=pin),
                patch("tools.cache_bundle.urlopen", side_effect=AssertionError("network used")),
                self.assertRaises(CacheError),
            ):
                provision_from_catalog(
                    url,
                    pin,
                    self.cache,
                    tool="fixture",
                    version="1.2.3",
                    platform="windows",
                    arch="x86_64",
                )


if __name__ == "__main__":
    unittest.main()
