from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import py7zr
import zstandard

from tools.build_bundle import (
    BundleError,
    _audit_native_tree,
    _extract_archive,
    _materialize_links,
    _normalize_machine,
    _read_package_definition,
    _seven_zip_entries,
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
    package_file = directory / "package.py"
    package_file.write_bytes(
        b"name = 'fixture'\nversion = '1.2.3'\ntools = ['fixture']\n"
        b"requires = ['platform-windows', 'arch-x86_64']\n\n"
        b"def commands():\n    env.PATH.prepend('{root}/payload/bin')\n"
    )
    return {
        "schema_version": 1,
        "tool": "fixture",
        "version": "1.2.3",
        "release_date": "2026-10-04",
        "upstream_manifest": "https://example.invalid/SHA256SUMS",
        "compatibility": {"rez_next": ">=0.3.6", "vx_rez_adapter": ">=0.1.0"},
        "package": {
            "definition": {"source": "package.py", "sha256": digest(package_file)},
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

    def pin_package(self, contents: bytes) -> None:
        source = self.root / "package.py"
        source.write_bytes(contents)
        self.definition["package"]["definition"]["sha256"] = digest(source)

    def test_copies_actual_package_definition_bytes_and_semantics_without_execution(self) -> None:
        contents = (
            b"# checked-in package definition\r\n"
            b"name: str = 'fixture'\r\nversion = '1.2.3'\r\n"
            b"requires = ['python-3.7+', 'library-2']\r\n"
            b"variants = [['platform-windows', 'arch-x86_64']]\r\n"
            b"tools = ['actual-command']\r\n\r\n"
            b"def commands():\r\n"
            b"    env.PATH.prepend('{root}/payload/actual-bin')\r\n"
            b"    env.FIXTURE_SETTING.set('actual setting')\r\n\r\n"
            b"raise AssertionError('the builder must never execute this source')\r\n"
        )
        self.pin_package(contents)
        asset = self.build()
        unpack(asset, self.root / "actual-definition")
        package = self.root / "actual-definition/fixture/1.2.3"
        self.assertEqual((package / "package.py").read_bytes(), contents)
        provenance = json.loads((package / "provenance.json").read_text())
        self.assertEqual(provenance["package_definition"], self.definition["package"]["definition"])
        self.assertIn(
            f"{hashlib.sha256(contents).hexdigest()}  fixture/1.2.3/package.py",
            (package / "sha256sums.txt").read_text(),
        )

    def test_package_definition_hash_is_checked_before_payload_extraction(self) -> None:
        (self.root / "package.py").write_bytes(b"name = 'changed'\n")
        with (
            patch("tools.build_bundle._install_payload") as install,
            self.assertRaisesRegex(BundleError, "package definition checksum mismatch"),
        ):
            self.build()
        install.assert_not_called()

    def test_package_definition_is_mandatory_and_uses_contained_regular_source(self) -> None:
        specification = self.definition["package"].pop("definition")
        with self.assertRaisesRegex(BundleError, "validation failed"):
            self.build()
        self.definition["package"]["definition"] = specification
        specification["source"] = "../package.py"
        with self.assertRaisesRegex(BundleError, "unsafe relative path"):
            self.build()
        specification["source"] = "directory"
        (self.root / "directory").mkdir()
        with self.assertRaisesRegex(BundleError, "regular file"):
            self.build()
        specification["source"] = "package.py"
        with self.assertRaisesRegex(BundleError, "metadata_directory is required"):
            _read_package_definition(self.definition, None)

    def test_package_definition_rejects_dynamic_duplicate_and_rebound_identities(self) -> None:
        base = "name = 'fixture'\nversion = '1.2.3'\n"
        rebinding = (
            "version = '1.2.3'\n",
            "if True:\n    version = '1.2.3'\n",
            "version += '-other'\n",
            "import os as version\n",
            "from os import name\n",
            "from os import *\n",
            "def name():\n    pass\n",
            "class version:\n    pass\n",
            "try:\n    pass\nexcept Exception as version:\n    pass\n",
            "match object():\n    case {'value': version}:\n        pass\n",
            "del version\n",
            "def helper(value=(version := 'other')):\n    pass\n",
            "(lambda value=(version := 'other'): value)\n",
            "def commands():\n    global version\n",
        )
        cases = [base + suffix for suffix in rebinding] + [
            "name = 'fixture'\nversion = str('1.2.3')\n",
            "name = 'other'\nversion = '1.2.3'\n",
            "name = 'fixture'\nversion = 123\n",
            "name = 'fixture'\n",
            "name = 'fixture'\nversion =\n",
        ]
        for contents in cases:
            with self.subTest(contents=contents):
                self.pin_package(contents.encode())
                with self.assertRaisesRegex(BundleError, "package definition"):
                    _read_package_definition(self.definition, self.root)

    def test_package_definition_allows_local_identity_names_and_keeps_source_unchanged(
        self,
    ) -> None:
        contents = (
            b"name = 'fixture'\nversion: str = '1.2.3'\n"
            b"def commands():\n"
            b"    version = 'local version'\n    name = 'local name'\n"
            b"    env.FIXTURE_SETTING.set(version)\n"
            b"class Helper:\n    version = 'class version'\n"
            b"values = [version for version in ('comprehension local',)]\n"
        )
        self.pin_package(contents)
        self.assertEqual(_read_package_definition(self.definition, self.root), contents)

    def test_supports_zip_tar_zstd_and_7z_with_the_same_contract(self) -> None:
        for archive_format in ("zip", "tar", "tar.zst", "7z"):
            with self.subTest(archive_format=archive_format):
                source = self.root / f"source.{archive_format}"
                if archive_format == "zip":
                    with zipfile.ZipFile(source, "w") as archive:
                        archive.writestr("bin/fixture.exe", b"executable")
                elif archive_format == "7z":
                    with py7zr.SevenZipFile(source, "w") as archive:
                        archive.writestr(b"executable", "bin/fixture.exe")
                else:
                    with tarfile.open(
                        source, "w:gz" if archive_format == "tar" else "w"
                    ) as archive:
                        member = tarfile.TarInfo("bin/fixture.exe")
                        member.size = 10
                        archive.addfile(member, io.BytesIO(b"executable"))
                    if archive_format == "tar.zst":
                        source.write_bytes(zstandard.ZstdCompressor().compress(source.read_bytes()))
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

    def test_7z_directory_mapping_preserves_resources_and_executable_intent(self) -> None:
        source = self.root / "application.7z"
        with py7zr.SevenZipFile(source, "w") as archive:
            archive.writestr(b"executable", "app/bin/fixture.exe")
            archive.files[0].file_properties()["attributes"] = 0x8020 | (
                (stat.S_IFREG | 0o755) << 16
            )
            archive.writestr(b"resource", "app/resources/data")
        definition = recipe(self.root, source, "7z")
        definition["targets"][0]["payload"]["mappings"] = [{"source": "app", "destination": "."}]
        asset = self.build(definition, source)
        unpack(asset, self.root / "7z-app")
        self.assertEqual(
            (self.root / "7z-app/fixture/1.2.3/payload/resources/data").read_bytes(), b"resource"
        )
        self.assertEqual(archive_modes(asset)["fixture/1.2.3/payload/bin/fixture.exe"], 0o755)

    def test_7z_rejects_unsafe_names_before_any_payload_extraction(self) -> None:
        cases = [
            ["../outside"],
            ["/absolute"],
            ["C:/escape"],
            ["payload:stream"],
            ["CON.txt"],
            ["COM¹.txt"],
            ["LPT³"],
            ["CONIN$"],
            ["name."],
            ["file", "FILE"],
            ["Dir/file", "dir/other"],
            ["file", "file"],
            ["file", "file/child"],
        ]
        for index, names in enumerate(cases):
            with self.subTest(names=names):
                source = self.root / f"unsafe-{index}.7z"
                with py7zr.SevenZipFile(source, "w") as archive:
                    for item, name in enumerate(names):
                        archive.writestr(b"data", f"entry-{item}")
                        archive.files[item].file_properties()["filename"] = name
                for decoder in ("py7zr", "native-7zip"):
                    with (
                        patch.object(py7zr.SevenZipFile, "extractall") as extract,
                        patch("tools.build_bundle.subprocess.run") as native,
                        self.assertRaises(BundleError),
                    ):
                        _extract_archive(
                            source,
                            self.root / f"unsafe-output-{index}-{decoder}",
                            "7z",
                            decoder=decoder,
                        )
                    extract.assert_not_called()
                    native.assert_not_called()
                self.assertFalse((self.root / "outside").exists())

    def test_7z_rejects_links_devices_and_missing_type_metadata_before_extraction(self) -> None:
        attributes = [
            0x0420,
            0x0410,
            0x0040,
            None,
            0x8020 | ((stat.S_IFLNK | 0o777) << 16),
            0x8020 | ((stat.S_IFIFO | 0o644) << 16),
            0x8020 | ((stat.S_IFCHR | 0o644) << 16),
            0x8020 | ((stat.S_IFSOCK | 0o644) << 16),
            0x8010 | ((stat.S_IFREG | 0o644) << 16),
        ]
        for index, flags in enumerate(attributes):
            with self.subTest(attributes=flags):
                source = self.root / f"special-{index}.7z"
                with py7zr.SevenZipFile(source, "w") as archive:
                    archive.writestr(b"link target or data", "member")
                    archive.files[0].file_properties()["attributes"] = flags
                for decoder in ("py7zr", "native-7zip"):
                    with (
                        patch.object(py7zr.SevenZipFile, "extractall") as extract,
                        patch("tools.build_bundle.subprocess.run") as native,
                        self.assertRaises(BundleError),
                    ):
                        _extract_archive(
                            source,
                            self.root / f"special-output-{index}-{decoder}",
                            "7z",
                            decoder=decoder,
                        )
                    extract.assert_not_called()
                    native.assert_not_called()

    def test_7z_rejects_hardlink_and_start_position_metadata(self) -> None:
        for special in ({"hardlink": "target"}, {"is_hardlink": True}, {"startpos": 0}):
            member = SimpleNamespace(
                filename="file",
                is_directory=False,
                is_file=True,
                is_symlink=False,
                is_junction=False,
                is_socket=False,
                file_properties=lambda extra=special: {"attributes": 0x0020, **extra},
            )
            with self.subTest(special=special), self.assertRaisesRegex(BundleError, "metadata"):
                _seven_zip_entries(SimpleNamespace(files=[member]))

    def test_7z_hash_is_checked_before_opening_and_malformed_streams_fail_closed(self) -> None:
        definition = recipe(self.root, self.source, "7z")
        definition["targets"][0]["upstream"]["sha256"] = "0" * 64
        with (
            patch.object(py7zr, "SevenZipFile") as open_archive,
            self.assertRaisesRegex(BundleError, "checksum mismatch"),
        ):
            self.build(definition)
        open_archive.assert_not_called()
        with self.assertRaisesRegex(BundleError, "safely extract"):
            _extract_archive(self.source, self.root / "malformed-7z", "7z")

    def test_explicit_native_7zip_extracts_regular_resources_with_the_same_contract(self) -> None:
        source = self.root / "native.7z"
        empty = self.root / "empty"
        empty.mkdir()
        with py7zr.SevenZipFile(source, "w") as archive:
            archive.writestr(b"executable", "app/bin/fixture.exe")
            archive.files[0].file_properties()["attributes"] = 0x8020 | (
                (stat.S_IFREG | 0o755) << 16
            )
            archive.writestr(b"resource", "app/resources/data")
            archive.write(empty, "app/empty")

        def native(command, **kwargs):
            if command == ["vx", "7zip", "i"]:
                return subprocess.CompletedProcess(command, 0, "7-Zip 26.04 (x64) : official", "")
            self.assertEqual(command[:3], ["vx", "7zip", "x"])
            self.assertEqual(command[-2:], ["--", str(source.resolve())])
            for switch in ("-t7z", "-sns-", "-snh-", "-snl-", "-spd", "-spod"):
                self.assertIn(switch, command)
            self.assertIs(kwargs["shell"], False)
            self.assertIs(kwargs["check"], True)
            self.assertEqual(kwargs["timeout"], 600)
            destination = Path(kwargs["cwd"])
            self.assertIn(f"-o{destination.resolve()}", command)
            (destination / "app/bin").mkdir(parents=True)
            (destination / "app/bin/fixture.exe").write_bytes(b"executable")
            (destination / "app/resources").mkdir()
            (destination / "app/resources/data").write_bytes(b"resource")
            (destination / "app/empty").mkdir()
            return subprocess.CompletedProcess(command, 0, "Everything is Ok", "")

        definition = recipe(self.root, source, "7z")
        definition["targets"][0]["payload"] = {
            "format": "7z",
            "decoder": "native-7zip",
            "mappings": [{"source": "app", "destination": "."}],
        }
        with patch("tools.build_bundle.subprocess.run", side_effect=native) as run:
            asset = self.build(definition, source)
        self.assertEqual(run.call_count, 2)
        unpack(asset, self.root / "native-result")
        payload = self.root / "native-result/fixture/1.2.3/payload"
        self.assertEqual((payload / "resources/data").read_bytes(), b"resource")
        self.assertTrue((payload / "empty").is_dir())
        self.assertEqual(archive_modes(asset)["fixture/1.2.3/payload/bin/fixture.exe"], 0o755)

    def test_native_7zip_rejects_old_or_unidentified_versions_before_extraction(self) -> None:
        source = self.root / "version.7z"
        with py7zr.SevenZipFile(source, "w") as archive:
            archive.writestr(b"data", "member")
        for index, banner in enumerate(("7-Zip 26.02 (x64)", "p7zip 16.02", "unknown")):
            with (
                self.subTest(banner=banner),
                patch(
                    "tools.build_bundle.subprocess.run",
                    return_value=subprocess.CompletedProcess([], 0, banner, ""),
                ) as run,
                self.assertRaisesRegex(BundleError, "26.04 or newer"),
            ):
                _extract_archive(
                    source, self.root / f"version-{index}", "7z", decoder="native-7zip"
                )
            self.assertEqual(run.call_count, 1)

    def test_native_7zip_nonzero_exit_and_timeout_fail_closed(self) -> None:
        source = self.root / "failed.7z"
        with py7zr.SevenZipFile(source, "w") as archive:
            archive.writestr(b"data", "member")
        errors = (
            subprocess.CalledProcessError(2, ["vx", "7zip"], stderr="CRC failed"),
            subprocess.TimeoutExpired(["vx", "7zip"], 600),
        )
        for index, error in enumerate(errors):
            with (
                self.subTest(error=type(error).__name__),
                patch(
                    "tools.build_bundle.subprocess.run",
                    side_effect=[
                        subprocess.CompletedProcess([], 0, "7-Zip (z) 26.04 : official", ""),
                        error,
                    ],
                ),
                self.assertRaisesRegex(BundleError, "exit code 2|timeout"),
            ):
                _extract_archive(source, self.root / f"failed-{index}", "7z", decoder="native-7zip")

    def test_native_7zip_rejects_missing_unexpected_and_wrong_type_results(self) -> None:
        source = self.root / "tree.7z"
        with py7zr.SevenZipFile(source, "w") as archive:
            archive.writestr(b"data", "member")
        for mode in ("missing", "unexpected", "directory"):

            def native(command, *, result=mode, **kwargs):
                if command[-1] == "i":
                    return subprocess.CompletedProcess(command, 0, "7-Zip 26.04 : official", "")
                destination = Path(kwargs["cwd"])
                if result == "unexpected":
                    (destination / "extra").write_bytes(b"unexpected")
                elif result == "directory":
                    (destination / "member").mkdir()
                return subprocess.CompletedProcess(command, 0, "Everything is Ok", "")

            with (
                self.subTest(mode=mode),
                patch("tools.build_bundle.subprocess.run", side_effect=native),
                self.assertRaisesRegex(BundleError, "omitted|unexpected"),
            ):
                _extract_archive(source, self.root / f"tree-{mode}", "7z", decoder="native-7zip")

    def test_native_7zip_rejects_extracted_hardlinks(self) -> None:
        source = self.root / "link.7z"
        with py7zr.SevenZipFile(source, "w") as archive:
            archive.writestr(b"data", "member")

        def native(command, **kwargs):
            if command[-1] == "i":
                return subprocess.CompletedProcess(command, 0, "7-Zip 26.04 : official", "")
            os.link(self.source, Path(kwargs["cwd"]) / "member")
            return subprocess.CompletedProcess(command, 0, "Everything is Ok", "")

        with (
            patch("tools.build_bundle.subprocess.run", side_effect=native),
            self.assertRaisesRegex(BundleError, "link or special"),
        ):
            _extract_archive(source, self.root / "native-link", "7z", decoder="native-7zip")

    def test_native_tree_uses_real_link_counts_when_directory_cache_reports_zero(self) -> None:
        destination = self.root / "cached-directory-metadata"
        destination.mkdir()
        member = destination / "member"
        member.write_bytes(b"regular file")
        cached = SimpleNamespace(st_mode=stat.S_IFREG | 0o644, st_nlink=0)
        entry = SimpleNamespace(path=str(member), stat=Mock(return_value=cached))
        with patch("tools.build_bundle.os.scandir") as scan:
            scan.return_value.__enter__.return_value = [entry]
            _audit_native_tree(destination, [("member", "file", None)])
            member.unlink()
            os.link(self.source, member)
            with self.assertRaisesRegex(BundleError, "link or special"):
                _audit_native_tree(destination, [("member", "file", None)])
        entry.stat.assert_not_called()

    def test_py7zr_unsupported_codec_requires_explicit_native_selection(self) -> None:
        source = self.root / "codec.7z"
        with py7zr.SevenZipFile(source, "w") as archive:
            archive.writestr(b"data", "member")
        with (
            patch.object(
                py7zr.SevenZipFile,
                "archiveinfo",
                return_value=SimpleNamespace(method_names=["LZMA2", "BCJ2*"]),
            ),
            patch.object(py7zr.SevenZipFile, "extractall") as extract,
            patch("tools.build_bundle.subprocess.run") as native,
            self.assertRaisesRegex(BundleError, "BCJ2.*explicitly"),
        ):
            _extract_archive(source, self.root / "codec-result", "7z")
        extract.assert_not_called()
        native.assert_not_called()

    def test_decoder_option_is_only_valid_for_7z_payloads(self) -> None:
        self.definition["targets"][0]["payload"]["decoder"] = "native-7zip"
        with self.assertRaisesRegex(BundleError, "validation failed"):
            self.build()

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

    def test_rejects_traversal_before_extracting_tar_zip_or_tar_zstd(self) -> None:
        for archive_format in ("zip", "tar", "tar.zst"):
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
                    if archive_format == "tar.zst":
                        source.write_bytes(zstandard.ZstdCompressor().compress(source.read_bytes()))
                with self.assertRaisesRegex(BundleError, "unsafe relative path"):
                    _extract_archive(
                        source, self.root / f"extract-{archive_format}", archive_format
                    )
                self.assertFalse((self.root / "outside").exists())

    def test_tar_zstd_checks_hash_before_decompression_and_rejects_malformed_frames(self) -> None:
        definition = recipe(self.root, self.source, "tar.zst")
        definition["targets"][0]["upstream"]["sha256"] = "0" * 64
        with (
            patch("tools.build_bundle._open_tar_archive") as open_archive,
            self.assertRaisesRegex(BundleError, "checksum mismatch"),
        ):
            self.build(definition)
        open_archive.assert_not_called()
        with self.assertRaisesRegex(BundleError, "safely extract"):
            _extract_archive(self.source, self.root / "malformed-zstd", "tar.zst")

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

    def test_smoke_writes_only_to_an_isolated_copy_and_home(self) -> None:
        observed_homes = []

        def mutating_smoke(command, **kwargs):
            working = Path(kwargs["cwd"])
            (working / "created-by-smoke").write_text("must not ship", encoding="utf-8")
            home = Path(kwargs["env"]["HOME"])
            observed_homes.append(home)
            (home / "configuration").write_text("must not persist", encoding="utf-8")
            self.assertEqual(kwargs["env"]["PYTHONDONTWRITEBYTECODE"], "1")
            self.assertNotIn("PYTHONPATH", kwargs["env"])
            return subprocess.CompletedProcess(command, 0, "fixture 1.2.3", "")

        with (
            patch("tools.build_bundle.host_platform.system", return_value="Windows"),
            patch("tools.build_bundle.host_platform.machine", return_value="AMD64"),
            patch("tools.build_bundle.subprocess.run", side_effect=mutating_smoke),
        ):
            asset = self.build(smoke_test=True)
        clean = self.build(output="without-smoke")
        self.assertEqual(asset.read_bytes(), clean.read_bytes())
        self.assertFalse(any(home.exists() for home in observed_homes))
        self.assertFalse(any("created-by-smoke" in name for name in archive_modes(asset)))

    def test_target_smoke_override_uses_its_command_expectation_and_timeout(self) -> None:
        self.definition["package"]["smoke_test"] = {
            "command": ["{root}/payload/default-does-not-exist"],
            "expect": "package default must not run",
        }
        self.definition["targets"][0]["smoke_test"] = {
            "command": ["{root}/payload/bin/fixture{exe}", "--target-version"],
            "expect": "target override {version}",
            "timeout_seconds": 123,
        }
        with (
            patch("tools.build_bundle.host_platform.system", return_value="Windows"),
            patch("tools.build_bundle.host_platform.machine", return_value="AMD64"),
            patch(
                "tools.build_bundle.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "target override 1.2.3", ""),
            ) as run,
        ):
            self.build(smoke_test=True)
        self.assertEqual(run.call_args.args[0][1:], ["--target-version"])
        self.assertEqual(run.call_args.kwargs["timeout"], 123)

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
