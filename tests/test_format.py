"""Tests for the bundle generator and the repository validator.

Run with ``python -m unittest discover -s tests`` or ``python tests/test_format.py``.
The tests build throwaway bundles in a temporary directory, so they never touch
the sample bundle committed under ``bundles/``.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import make_bundle  # noqa: E402
import validate_repo  # noqa: E402


def write_package(directory: Path, name: str = "python", version: str = "3.11.9") -> Path:
    """Create a minimal rez package tree and return its root."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "package.py").write_text(
        f'name = "{name}"\nversion = "{version}"\n\nrequires = []\n',
        encoding="utf-8",
    )
    (directory / "python.exe").write_text("@echo off\nrem sample\n", encoding="utf-8")
    return directory


class MakeBundleTests(unittest.TestCase):
    """The generator produces bundles the validator accepts."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_reads_identity_from_package_py(self) -> None:
        write_package(self.tmp / "src" / "python", "maya", "2024.1")
        identity = make_bundle.read_identity(self.tmp / "src" / "python" / "package.py")
        self.assertEqual(identity.name, "maya")
        self.assertEqual(identity.version, "2024.1")

    def test_rejects_source_without_package_py(self) -> None:
        source = self.tmp / "empty"
        source.mkdir()
        with self.assertRaises(make_bundle.BundleError):
            make_bundle.read_identity(source / "package.py")

    def test_rejects_unknown_platform(self) -> None:
        with self.assertRaises(make_bundle.BundleError):
            make_bundle.build_bundle(self.tmp, self.tmp / "src", "solaris-sparc")

    def test_generated_bundle_validates(self) -> None:
        repo = self.tmp / "repo"
        for folder in ("schema", "scripts"):
            (repo / folder).mkdir(parents=True)
        for schema in ("bundle.schema.json", "index.schema.json"):
            shutil.copy(REPO_ROOT / "schema" / schema, repo / "schema" / schema)

        source = write_package(repo / "examples" / "src" / "python")
        bundle_file = make_bundle.build_bundle(repo, source, "windows-x86_64")
        make_bundle.regenerate_index(repo)

        self.assertTrue(bundle_file.is_file())
        self.assertEqual(validate_repo.main(["--repo-root", str(repo)]), 0)

    def test_bundle_records_rez_package_root(self) -> None:
        repo = self.tmp / "repo"
        source = write_package(repo / "src" / "python")
        bundle_file = make_bundle.build_bundle(repo, source, "linux-x86_64")

        bundle = json.loads(bundle_file.read_text(encoding="utf-8"))
        self.assertEqual(bundle["rez"]["layout"], "rez-package-root")
        self.assertEqual(bundle["rez"]["package_root"], "python/3.11.9")
        self.assertEqual(bundle["rez"]["install_root"], "python/3.11.9")
        self.assertEqual(bundle["rez"]["package_file"], "package.py")

    def test_archives_contain_rez_layout(self) -> None:
        repo = self.tmp / "repo"
        source = write_package(repo / "src" / "python")
        bundle_file = make_bundle.build_bundle(repo, source, "windows-x86_64")
        bundle = json.loads(bundle_file.read_text(encoding="utf-8"))

        for asset in bundle["assets"]:
            archive = bundle_file.parent / "assets" / asset["file_name"]
            if asset["format"] == "zip":
                names = zipfile.ZipFile(archive).namelist()
            else:
                with tarfile.open(archive, "r:gz") as tar:
                    names = tar.getnames()
            self.assertIn("python/3.11.9/package.py", names)

    def test_archives_are_reproducible(self) -> None:
        repo = self.tmp / "repo"
        source = write_package(repo / "src" / "python")
        first = make_bundle.build_bundle(repo, source, "windows-x86_64")
        first_digests = {
            asset["file_name"]: asset["sha256"]
            for asset in json.loads(first.read_text(encoding="utf-8"))["assets"]
        }

        second = make_bundle.build_bundle(repo, source, "windows-x86_64")
        second_digests = {
            asset["file_name"]: asset["sha256"]
            for asset in json.loads(second.read_text(encoding="utf-8"))["assets"]
        }
        self.assertEqual(first_digests, second_digests)


class ValidateRepoTests(unittest.TestCase):
    """The validator catches malformed bundles and stale indexes."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "schema").mkdir()
        for schema in ("bundle.schema.json", "index.schema.json"):
            shutil.copy(REPO_ROOT / "schema" / schema, self.tmp / "schema" / schema)
        self.bundle_schema = validate_repo.load_schema(
            self.tmp / "schema" / "bundle.schema.json"
        )
        self.index_schema = validate_repo.load_schema(
            self.tmp / "schema" / "index.schema.json"
        )

    def build_sample(self) -> Path:
        repo = self.tmp
        source = write_package(repo / "examples" / "src" / "python")
        make_bundle.build_bundle(repo, source, "windows-x86_64")
        make_bundle.regenerate_index(repo)
        return repo / "bundles" / "windows-x86_64" / "python" / "3.11.9"

    def test_valid_bundle_passes(self) -> None:
        self.build_sample()
        self.assertEqual(validate_repo.main(["--repo-root", str(self.tmp)]), 0)

    def test_detects_identity_directory_mismatch(self) -> None:
        bundle_dir = self.build_sample()
        bundle_file = bundle_dir / "bundle.json"
        bundle = json.loads(bundle_file.read_text(encoding="utf-8"))
        bundle["version"] = "3.12.0"
        bundle_file.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

        errors: list[str] = []
        validate_repo.check_bundle(
            self.tmp, bundle_dir, "windows-x86_64", "python", "3.11.9",
            self.bundle_schema, errors,
        )
        self.assertTrue(any("version" in err for err in errors))

    def test_detects_bad_checksum(self) -> None:
        bundle_dir = self.build_sample()
        bundle_file = bundle_dir / "bundle.json"
        bundle = json.loads(bundle_file.read_text(encoding="utf-8"))
        bundle["assets"][0]["sha256"] = "0" * 64
        bundle_file.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

        errors: list[str] = []
        validate_repo.check_bundle(
            self.tmp, bundle_dir, "windows-x86_64", "python", "3.11.9",
            self.bundle_schema, errors,
        )
        self.assertTrue(any("sha256" in err for err in errors))

    def test_detects_stale_index(self) -> None:
        self.build_sample()
        index_file = self.tmp / "index.json"
        index = json.loads(index_file.read_text(encoding="utf-8"))
        index["packages"] = []
        index_file.write_text(json.dumps(index, indent=2), encoding="utf-8")

        self.assertNotEqual(validate_repo.main(["--repo-root", str(self.tmp)]), 0)

    def test_detects_missing_package_py_in_archive(self) -> None:
        """An archive without <name>/<version>/package.py breaks the adapter chain."""
        bundle_dir = self.build_sample()
        archive = bundle_dir / "assets" / "python-3.11.9-windows-x86_64.tar.gz"

        # Rewrite the archive with a flattened layout.
        with tarfile.open(archive, "r:gz") as src:
            members = [(m, src.extractfile(m).read()) for m in src.getmembers()]
        with tarfile.open(archive, "w:gz") as out:
            for info, payload in members:
                info.name = Path(info.name).name
                info.size = len(payload)
                out.addfile(info, io.BytesIO(payload))

        bundle = json.loads((bundle_dir / "bundle.json").read_text(encoding="utf-8"))
        errors: list[str] = []
        validate_repo.check_archive_layout(
            bundle_dir, archive, bundle["assets"][0], bundle, "assets[0]", errors
        )
        self.assertTrue(any("does not contain" in err for err in errors))


class CommittedRepoTests(unittest.TestCase):
    """The sample bundle committed to this repository is valid."""

    def test_committed_repo_validates(self) -> None:
        self.assertEqual(validate_repo.main(["--repo-root", str(REPO_ROOT)]), 0)

    def test_validator_cli_exits_zero(self) -> None:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "validate_repo.py")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
