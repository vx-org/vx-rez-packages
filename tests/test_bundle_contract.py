from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import zstandard

from tools.build_bundle import (
    BundleError,
    _extract_archive,
    _materialize_links,
    _normalize_machine,
    _validate_archive_entries,
    build_bundle,
    load_definition,
)
from tools.collect_notices import collect_notices
from tools.generate_index import generate_index_from_directory, generate_index_from_release

TRIPLE = "x86_64-pc-windows-msvc"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recipe(directory: Path, source: Path, archive_format: str = "binary") -> dict:
    license_file = directory / "LICENSE"
    license_file.write_text("Fixture upstream license\n", encoding="utf-8")
    return {
        "schema_version": 1,
        "tool": "fixture",
        "version": "1.2.3",
        "release_date": "2026-10-04",
        "upstream_manifest": "https://example.invalid/SHA256SUMS",
        "compatibility": {"rez_next": ">=0.3.6", "vx_rez_adapter": ">=0.1.0"},
        "package": {
            "description": "Contract test runtime",
            "tools": ["fixture"],
            "path_entries": ["payload/bin"],
            "smoke_test": {
                "command": ["{root}/payload/bin/fixture{exe}", "--version"],
                "expect": "fixture {version}",
            },
        },
        "provenance": {
            "repository": "https://example.invalid/fixture",
            "revision": "1" * 40,
            "license": "MIT",
            "source_url": "https://example.invalid/fixture-source.tar.gz",
            "source_sha256": "2" * 64,
        },
        "metadata": [
            {"source": "LICENSE", "destination": "LICENSE", "sha256": digest(license_file)}
        ],
        "targets": [
            {
                "triple": TRIPLE,
                "platform": "windows",
                "arch": "x86_64",
                "runner": "windows-2025",
                "status": "supported",
                "upstream": {"url": "https://example.invalid/payload", "sha256": digest(source)},
                "payload": {
                    "format": archive_format,
                    "mappings": [
                        {
                            "source": "." if archive_format == "binary" else "bin/fixture.exe",
                            "destination": "bin/fixture.exe",
                            "executable": True,
                        }
                    ],
                },
            }
        ],
        "unsupported_targets": [
            {
                "triple": "i686-pc-windows-msvc",
                "status": "unsupported",
                "reason": "No upstream fixture asset.",
            }
        ],
    }


def unpack(archive: Path, destination: Path) -> None:
    destination.mkdir()
    with (
        archive.open("rb") as source,
        zstandard.ZstdDecompressor().stream_reader(source) as reader,
        tarfile.open(fileobj=reader, mode="r|") as bundle,
    ):
        bundle.extractall(destination, filter="data")


def archive_modes(archive: Path) -> dict[str, int]:
    with (
        archive.open("rb") as source,
        zstandard.ZstdDecompressor().stream_reader(source) as reader,
        tarfile.open(fileobj=reader, mode="r|") as bundle,
    ):
        return {member.name: member.mode for member in bundle}


class BundleContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "binary"
        self.source.write_bytes(b"real payload bytes for an offline test\n")
        self.definition = recipe(self.root, self.source)

    def build(
        self,
        definition: dict | None = None,
        source: Path | None = None,
        output: str = "dist",
        smoke_test: bool = False,
    ) -> Path:
        return build_bundle(
            definition or self.definition,
            TRIPLE,
            self.root / output,
            source_archive=source or self.source,
            metadata_directory=self.root,
            smoke_test=smoke_test,
        )

    def test_builds_deterministic_real_package_with_complete_checksums(self) -> None:
        first = self.build()
        self.source.touch()
        second = self.build(output="second")
        self.assertEqual(first.read_bytes(), second.read_bytes())
        original_gettarinfo = tarfile.TarFile.gettarinfo

        def without_posix_mode(archive, *args, **kwargs):
            info = original_gettarinfo(archive, *args, **kwargs)
            info.mode = 0o644
            return info

        with patch.object(tarfile.TarFile, "gettarinfo", new=without_posix_mode):
            windows_modes = self.build(output="windows-modes")
        self.assertEqual(first.read_bytes(), windows_modes.read_bytes())
        self.assertEqual(archive_modes(first)["fixture/1.2.3/payload/bin/fixture.exe"], 0o755)
        unpack(first, self.root / "unpacked")
        repository = self.root / "unpacked"
        package = repository / "fixture" / "1.2.3"
        self.assertEqual(
            (package / "payload/bin/fixture.exe").read_bytes(), self.source.read_bytes()
        )
        package_text = (package / "package.py").read_text()
        self.assertIn("tools = ['fixture']", package_text)
        self.assertIn("env.PATH.prepend('{root}/payload/bin')", package_text)
        self.assertIn("platform-windows", package_text)
        self.assertTrue((repository / "platform/windows/package.py").is_file())
        self.assertTrue((repository / "arch/x86_64/package.py").is_file())
        self.assertEqual((package / "LICENSE").read_bytes(), (self.root / "LICENSE").read_bytes())
        manifest = json.loads((package / "manifest.json").read_text())
        self.assertEqual(manifest["package_root"], "fixture/1.2.3")
        self.assertEqual(manifest["upstream"]["archive_sha256"], digest(self.source))
        provenance = json.loads((package / "provenance.json").read_text())
        self.assertEqual(provenance["upstream"], self.definition["provenance"])
        checksum_file = package / "sha256sums.txt"
        listed = {}
        for line in checksum_file.read_text().splitlines():
            expected, relative = line.split("  ", 1)
            self.assertEqual(expected, digest(repository / relative))
            listed[relative] = expected
        actual = {
            path.relative_to(repository).as_posix()
            for path in repository.rglob("*")
            if path.is_file() and path != checksum_file
        }
        self.assertEqual(set(listed), actual)
        self.assertEqual(
            first.with_name(first.name + ".sha256").read_text(), f"{digest(first)}  {first.name}\n"
        )

    def test_supports_zip_and_tar_with_the_same_contract(self) -> None:
        for archive_format in ("zip", "tar"):
            with self.subTest(archive_format=archive_format):
                source = self.root / f"source.{archive_format}"
                if archive_format == "zip":
                    with zipfile.ZipFile(source, "w") as archive:
                        archive.writestr("bin/fixture.exe", b"executable")
                else:
                    with tarfile.open(source, "w:gz") as archive:
                        member = tarfile.TarInfo("bin/fixture.exe")
                        member.size = 10
                        archive.addfile(member, io.BytesIO(b"executable"))
                asset = self.build(
                    recipe(self.root, source, archive_format), source, output=archive_format
                )
                unpack(asset, self.root / f"unpacked-{archive_format}")
                self.assertEqual(
                    (
                        self.root
                        / f"unpacked-{archive_format}"
                        / "fixture/1.2.3/payload/bin/fixture.exe"
                    ).read_bytes(),
                    b"executable",
                )

    def test_whole_directory_mapping_preserves_application_resources(self) -> None:
        source = self.root / "application.zip"
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr("app/bin/fixture.exe", b"executable")
            archive.writestr("app/resources/data", b"resource")
        definition = recipe(self.root, source, "zip")
        definition["targets"][0]["payload"]["mappings"] = [{"source": "app", "destination": "."}]
        asset = self.build(definition, source)
        unpack(asset, self.root / "app")
        self.assertEqual(
            (self.root / "app/fixture/1.2.3/payload/resources/data").read_bytes(), b"resource"
        )

    def test_directory_mapping_preserves_upstream_executable_metadata(self) -> None:
        source = self.root / "application.tar"
        with tarfile.open(source, "w") as archive:
            member = tarfile.TarInfo("app/bin/fixture.exe")
            member.size = 10
            member.mode = 0o755
            archive.addfile(member, io.BytesIO(b"executable"))
        definition = recipe(self.root, source, "tar")
        definition["targets"][0]["payload"]["mappings"] = [{"source": "app", "destination": "."}]
        asset = self.build(definition, source)
        self.assertEqual(archive_modes(asset)["fixture/1.2.3/payload/bin/fixture.exe"], 0o755)

    def test_checks_upstream_hash_before_attempting_extraction(self) -> None:
        definition = recipe(self.root, self.source, "zip")
        definition["targets"][0]["upstream"]["sha256"] = "0" * 64
        with patch("tools.build_bundle._extract_archive") as extract:
            with self.assertRaisesRegex(BundleError, "checksum mismatch"):
                self.build(definition)
            extract.assert_not_called()

    def test_rejects_tampered_license(self) -> None:
        (self.root / "LICENSE").write_text("changed license", encoding="utf-8")
        with self.assertRaisesRegex(BundleError, "metadata checksum mismatch"):
            self.build()

    def test_rejects_traversal_before_extracting_tar_or_zip(self) -> None:
        for archive_format in ("zip", "tar"):
            with self.subTest(archive_format=archive_format):
                source = self.root / f"escape.{archive_format}"
                if archive_format == "zip":
                    with zipfile.ZipFile(source, "w") as archive:
                        archive.writestr("../outside", b"escape")
                else:
                    with tarfile.open(source, "w") as archive:
                        member = tarfile.TarInfo("../outside")
                        member.size = 6
                        archive.addfile(member, io.BytesIO(b"escape"))
                with self.assertRaisesRegex(BundleError, "unsafe relative path"):
                    _extract_archive(
                        source, self.root / f"extract-{archive_format}", archive_format
                    )
                self.assertFalse((self.root / "outside").exists())

    def test_rejects_escaping_links_cycles_and_non_directory_parents(self) -> None:
        cases = [
            [("bin/link", "symlink", "../../escape")],
            [("one", "symlink", "two"), ("two", "symlink", "one")],
            [("link", "symlink", "real"), ("real", "dir", None), ("link/child", "file", None)],
            [("link", "hardlink", "missing")],
        ]
        for entries in cases:
            with self.subTest(entries=entries), self.assertRaises(BundleError):
                _validate_archive_entries(entries)

    def test_allows_safe_internal_archive_links(self) -> None:
        _validate_archive_entries(
            [
                ("lib", "dir", None),
                ("lib/runtime.1", "file", None),
                ("lib/runtime", "symlink", "runtime.1"),
                ("copy", "hardlink", "lib/runtime.1"),
            ]
        )

    def test_materializes_internal_aliases_and_rejects_directory_cycles(self) -> None:
        payload = self.root / "links"
        payload.mkdir()
        (payload / "library").write_bytes(b"library content")
        alias = payload / "alias"
        try:
            alias.symlink_to("library")
        except OSError:
            self.skipTest("native symlink creation is unavailable")
        _materialize_links(payload)
        self.assertFalse(alias.is_symlink())
        self.assertEqual(alias.read_bytes(), b"library content")
        recursive = payload / "recursive"
        recursive.symlink_to(".", target_is_directory=True)
        with self.assertRaisesRegex(BundleError, "directory link cycle"):
            _materialize_links(payload)

    def test_rejects_duplicate_casefold_and_implicit_directory_collisions(self) -> None:
        for names in (("bin/file", "bin/file"), ("Bin/file", "bin/other"), ("FILE", "file")):
            with self.subTest(names=names), self.assertRaisesRegex(BundleError, "collision"):
                _validate_archive_entries([(name, "file", None) for name in names])

    def test_rejects_portability_and_special_file_attacks(self) -> None:
        for name in ("C:/escape", "bin\\escape", "/escape", "NUL", "file."):
            with self.subTest(name=name), self.assertRaises(BundleError):
                _validate_archive_entries([(name, "file", None)])
        source = self.root / "device.tar"
        with tarfile.open(source, "w") as archive:
            device = tarfile.TarInfo("device")
            device.type = tarfile.CHRTYPE
            archive.addfile(device)
        with self.assertRaisesRegex(BundleError, "unsupported tar member"):
            _extract_archive(source, self.root / "devices", "tar")

    def test_rejects_duplicate_targets_and_unsafe_recipe_paths(self) -> None:
        self.definition["targets"].append(self.definition["targets"][0])
        path = self.root / "recipe.json"
        path.write_text(json.dumps(self.definition), encoding="utf-8")
        with self.assertRaisesRegex(BundleError, "duplicate target"):
            load_definition(path)
        self.definition["targets"].pop()
        self.definition["package"]["path_entries"] = ["../outside"]
        with self.assertRaisesRegex(BundleError, "unsafe relative path"):
            self.build()

    def test_refuses_foreign_smoke_and_runs_declared_native_command(self) -> None:
        with (
            patch("tools.build_bundle.host_platform.system", return_value="Linux"),
            self.assertRaisesRegex(BundleError, "native target"),
        ):
            self.build(smoke_test=True)
        with (
            patch("tools.build_bundle.host_platform.system", return_value="Windows"),
            patch("tools.build_bundle.host_platform.machine", return_value="AMD64"),
            patch(
                "tools.build_bundle.subprocess.run",
                return_value=subprocess.CompletedProcess(["fixture.exe"], 0, "fixture 1.2.3", ""),
            ) as run,
        ):
            self.build(smoke_test=True)
            self.assertEqual(run.call_args.args[0][1:], ["--version"])
            self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_release_index_preserves_the_consumer_v1_contract(self) -> None:
        asset = self.build()
        index = generate_index_from_directory(
            self.definition,
            asset.parent,
            repository="vx-org/fixture",
            release_tag="fixture-1.2.3",
            generated_at="2026-10-04T00:00:00Z",
        )
        entry = index["bundles"][0]
        self.assertEqual(entry["sha256"], digest(asset))
        self.assertEqual(entry["bundle_schema_version"], 1)
        self.assertEqual(entry["package_root"], "fixture/1.2.3")
        release = {
            "tag_name": "fixture-1.2.3",
            "assets": [{"name": asset.name, "browser_download_url": entry["download_url"]}],
        }
        readback = generate_index_from_release(
            self.definition,
            release,
            {asset.name + ".sha256": asset.with_name(asset.name + ".sha256").read_text()},
            repository="vx-org/fixture",
            generated_at="2026-10-04T00:00:00Z",
        )
        self.assertEqual(index, readback)
        asset.write_bytes(b"tampered")
        with self.assertRaisesRegex(BundleError, "checksum mismatch"):
            generate_index_from_directory(
                self.definition,
                asset.parent,
                repository="vx-org/fixture",
                release_tag="fixture-1.2.3",
            )

    def test_collects_real_license_texts_from_verified_source(self) -> None:
        source = self.root / "source.tar.gz"
        with tarfile.open(source, "w:gz") as archive:
            for name, text in (
                ("source/LICENSE", b"upstream license"),
                ("source/vendor/dependency/NOTICE", b"dependency attribution"),
                ("source/main.go", b"not a legal notice"),
            ):
                member = tarfile.TarInfo(name)
                member.size = len(text)
                archive.addfile(member, io.BytesIO(text))
        output = self.root / "notices.txt"
        collected = collect_notices(
            source, digest(source), "https://example.invalid/source", output
        )
        self.assertEqual(collected, digest(output))
        self.assertIn("dependency attribution", output.read_text())
        self.assertIn("source/vendor/dependency/NOTICE", output.read_text())
        self.assertNotIn("not a legal notice", output.read_text())
        with self.assertRaisesRegex(BundleError, "checksum mismatch"):
            collect_notices(source, "0" * 64, "https://example.invalid/source", output)

    def test_normalizes_rez_architecture_names(self) -> None:
        for name in ("AMD64", "x64", "x86_64"):
            self.assertEqual(_normalize_machine(name), "x86_64")
        for name in ("arm64", "aarch64"):
            self.assertEqual(_normalize_machine(name), "arm_64")


if __name__ == "__main__":
    unittest.main()
