"""Exercise real cache verification around a mocked native adapter process boundary."""

from __future__ import annotations

import hashlib
import io
import json
import platform
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import zstandard

from tools.build_bundle import BundleError, _normalize_machine
from tools.cache_bundle import CacheError
from tools.verify_consumer import ConsumerError, _check_process_output, verify_consumer


def digest(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


class NativeConsumerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.cache = self.root / "fresh-cache"
        self.repository = self.root / "local-repository"
        self.platform = {"Windows": "windows", "Linux": "linux", "Darwin": "osx"}[platform.system()]
        self.arch = _normalize_machine(platform.machine())
        self.triple = "fixture-native"
        self.variant = f"fixture/1.2.3/platform-{self.platform}/arch-{self.arch}"
        self.payload = self.variant + "/payload"
        self.program = "fixture.exe" if self.platform == "windows" else "fixture"
        self.executable = self.payload + "/bin/" + self.program
        self.asset_name = "fixture-1.2.3-fixture-native.rez.tar.zst"
        self.selected = {
            "tool": "fixture",
            "version": "1.2.3",
            "platform": self.platform,
            "arch": self.arch,
            "triple": self.triple,
            "asset_name": self.asset_name,
            "package_root": "fixture/1.2.3",
        }
        manifest = {
            "schema_version": 1,
            **self.selected,
            "payload_root": self.payload,
            "upstream": {
                "manifest_url": "https://example.invalid/checksums",
                "archive_url": "https://example.invalid/runtime.zip",
                "archive_sha256": "a" * 64,
            },
            "checksums": {
                "algorithm": "sha256",
                "file": "fixture/1.2.3/sha256sums.txt",
                "scope": "all regular repository files except checksum list",
            },
            "compatibility": {"rez_next": ">=0", "vx_rez_adapter": ">=0"},
        }
        package = (
            "name = 'fixture'\nversion = '1.2.3'\n"
            f"variants = [['platform-{self.platform}', 'arch-{self.arch}']]\n"
            "def commands():\n    env.PATH.prepend('{root}/payload/bin')\n"
        ).encode()
        files = {
            "fixture/1.2.3/package.py": package,
            "fixture/1.2.3/manifest.json": json.dumps(manifest).encode(),
            "fixture/1.2.3/LICENSE": b"actual fixture license",
            self.executable: b"real fixture payload bytes; native process is mocked",
            f"platform/{self.platform}/package.py": (
                f"name = 'platform'\nversion = '{self.platform}'\n".encode()
            ),
            f"arch/{self.arch}/package.py": f"name = 'arch'\nversion = '{self.arch}'\n".encode(),
        }
        files["fixture/1.2.3/sha256sums.txt"] = "".join(
            f"{digest(contents)}  {name}\n" for name, contents in sorted(files.items())
        ).encode()
        with io.BytesIO() as stream:
            with tarfile.open(fileobj=stream, mode="w") as archive:
                for name, contents in sorted(files.items()):
                    file = self.repository / name
                    file.parent.mkdir(parents=True, exist_ok=True)
                    file.write_bytes(contents)
                    member = tarfile.TarInfo(name)
                    member.size = len(contents)
                    member.mode = 0o755 if name == self.executable else 0o644
                    archive.addfile(member, io.BytesIO(contents))
            bundle = zstandard.ZstdCompressor().compress(stream.getvalue())
        self.bundle_sha = digest(bundle)
        self.index_url = (
            "https://github.com/vx-org/fixture/releases/download/fixture-1.2.3-r1/index.json"
        )
        bundle_url = (
            "https://github.com/vx-org/fixture/releases/download/fixture-1.2.3-r1/"
            + self.asset_name
        )
        index = json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-10-09T00:00:00Z",
                "repository": "vx-org/fixture",
                "release_tag": "fixture-1.2.3-r1",
                "bundles": [
                    {
                        **self.selected,
                        "download_url": bundle_url,
                        "sha256": self.bundle_sha,
                        "bundle_schema_version": 1,
                    }
                ],
                "unsupported_targets": [],
            }
        ).encode()
        self.index_sha = digest(index)
        self.responses = {self.index_url: index, bundle_url: bundle}
        self.bundle_directory = self.root / "built-bundles"
        self.bundle_directory.mkdir()
        (self.bundle_directory / self.asset_name).write_bytes(bundle)
        (self.bundle_directory / (self.asset_name + ".sha256")).write_text(
            f"{self.bundle_sha}  {self.asset_name}\n", encoding="utf-8"
        )
        self.trusted_index = self.root / "trusted-index.json"
        self.trusted_index.write_bytes(index)
        self.trusted_index.with_name(self.trusted_index.name + ".sha256").write_text(
            f"{self.index_sha}  {self.trusted_index.name}\n", encoding="utf-8"
        )
        self.consumer = self.root / "reviewed-consumer"
        self.consumer.write_bytes(b"mock boundary; not executed")
        self.definition = {
            "schema_version": 1,
            "tool": "fixture",
            "version": "1.2.3",
            "build_revision": 1,
            "release_date": "2026-10-09",
            "upstream_manifest": "https://example.invalid/checksums",
            "compatibility": {"rez_next": ">=0", "vx_rez_adapter": ">=0"},
            "package": {
                "definition": {"source": "package.py", "sha256": digest(package)},
                "description": "native contract fixture",
                "tools": ["fixture"],
                "path_entries": ["payload/bin"],
                "smoke_test": {
                    "command": [
                        "{root}/payload/bin/fixture{exe}",
                        "argument with spaces",
                        "$(must stay literal)",
                    ],
                    "expect": "FIXTURE_NATIVE_OK",
                    "timeout_seconds": 60,
                },
            },
            "provenance": {
                "repository": "https://example.invalid/fixture",
                "revision": "a" * 40,
                "source_url": "https://example.invalid/source.tar.gz",
                "source_sha256": "b" * 64,
                "license": "MIT",
            },
            "metadata": [
                {
                    "source": "LICENSE",
                    "destination": "LICENSE",
                    "sha256": digest(files["fixture/1.2.3/LICENSE"]),
                }
            ],
            "targets": [
                {
                    "triple": self.triple,
                    "platform": self.platform,
                    "arch": self.arch,
                    "runner": "native",
                    "status": "supported",
                    "upstream": {"url": "https://example.invalid/runtime.zip", "sha256": "a" * 64},
                    "payload": {
                        "format": "binary",
                        "mappings": [
                            {"source": ".", "destination": "bin/fixture", "executable": True}
                        ],
                    },
                }
            ],
            "unsupported_targets": [],
        }
        self.requests = []

    def native_process(self, command, **kwargs):
        self.assertEqual(command[0], str(self.consumer))
        request = json.loads(Path(command[1]).read_text())
        self.requests.append(request)
        self.assertEqual(request["command"][1:], ["argument with spaces", "$(must stay literal)"])
        self.assertEqual(Path(request["executable"]).read_bytes(), self.responses_payload())
        self.assertFalse(Path(request["repository"]).is_relative_to(self.cache))
        self.assertEqual(request["expected_root"], str(kwargs["cwd"]))
        repository = Path(request["repository"])
        expected_environment = {
            "PATH": str(Path(request["expected_root"]) / "payload/bin"),
            "FIXTURE_ROOT": request["expected_root"],
            "FIXTURE_VERSION": "1.2.3",
            "PLATFORM_ROOT": str(repository / "platform" / self.platform),
            "PLATFORM_VERSION": self.platform,
            "ARCH_ROOT": str(repository / "arch" / self.arch),
            "ARCH_VERSION": self.arch,
        }
        self.assertEqual(request["expected_environment"], expected_environment)
        self.assertIn("VX_CONSUMER_PARENT_SENTINEL", kwargs["env"])
        self.assertFalse(kwargs["shell"])
        (Path(request["expected_root"]) / "created-only-by-smoke").write_bytes(
            b"must not enter the cache"
        )
        receipt = {
            "schema_version": 1,
            **{key: request[key] for key in ("tool", "version", "platform", "arch")},
            "selected_root": request["expected_root"],
            "executable": request["executable"],
            "sdk_version": "test-sdk",
            "environment_keys": [
                *expected_environment,
                "REZ_USED_REQUEST",
                "REZ_USED_RESOLVE",
                "REZ_USED_PACKAGES_NAMES",
                "REZ_USED_PACKAGES_PATH",
                "REZ_USED_VERSION",
                "REZ_USED_TIMESTAMP",
            ],
            "launches": ["direct", "bare"],
        }
        output = "\n".join(
            [
                "VX_REZ_CONSUMER_PHASE_BEGIN direct",
                "FIXTURE_NATIVE_OK",
                "VX_REZ_CONSUMER_PHASE_END direct",
                "VX_REZ_CONSUMER_PHASE_BEGIN bare",
                "FIXTURE_NATIVE_OK",
                "VX_REZ_CONSUMER_PHASE_END bare",
                "VX_REZ_CONSUMER_RECEIPT " + json.dumps(receipt),
                "",
            ]
        )
        return subprocess.CompletedProcess(command, 0, output, "")

    def responses_payload(self):
        return b"real fixture payload bytes; native process is mocked"

    def verify(self, **overrides):
        arguments = {
            "definition": self.definition,
            "triple": self.triple,
            "consumer_executable": self.consumer,
            "index_url": self.index_url,
            "index_sha256": self.index_sha,
            "cache": self.cache,
            "expected_sdk_version": "test-sdk",
            "require_empty_cache": True,
        }
        arguments.update(overrides)
        return verify_consumer(**arguments)

    def test_real_cache_chain_launches_only_private_variant_copies_then_rereads_offline(self):
        with (
            patch(
                "tools.cache_bundle.urlopen",
                side_effect=lambda url, **_: io.BytesIO(self.responses[url]),
            ) as download,
            patch("tools.verify_consumer.subprocess.run", side_effect=self.native_process),
        ):
            result = self.verify()
        self.assertEqual(download.call_count, 2)
        self.assertEqual(len(self.requests), 2)
        self.assertTrue(result["initial_cache_empty"])
        self.assertTrue(result["offline_cache_verified"])
        self.assertEqual(result["source_kind"], "pinned_release_index")
        self.assertEqual(result["native_runs"][0], result["native_runs"][1])
        self.assertEqual(result["native_runs"][0]["root_relative"], self.variant)
        self.assertFalse(any(self.cache.rglob("created-only-by-smoke")))
        self.assertFalse(any(Path(request["repository"]).exists() for request in self.requests))

    def test_offline_cache_corruption_stops_before_the_second_native_launch(self):
        def corrupt_after_launch(command, **kwargs):
            completed = self.native_process(command, **kwargs)
            (self.cache / "indexes" / self.index_sha).write_bytes(b"corrupt after native launch")
            return completed

        with (
            patch(
                "tools.cache_bundle.urlopen",
                side_effect=lambda url, **_: io.BytesIO(self.responses[url]),
            ) as download,
            patch("tools.verify_consumer.subprocess.run", side_effect=corrupt_after_launch),
            self.assertRaisesRegex(CacheError, "cached checksum mismatch"),
        ):
            self.verify()
        self.assertEqual(download.call_count, 2)
        self.assertEqual(len(self.requests), 1)

    def test_local_native_gate_reverifies_real_files_without_claiming_public_acquisition(self):
        with (
            patch("tools.cache_bundle.urlopen", side_effect=AssertionError("network used")),
            patch("tools.verify_consumer.subprocess.run", side_effect=self.native_process),
        ):
            result = verify_consumer(
                self.definition,
                self.triple,
                repository=self.repository,
                consumer_executable=self.consumer,
            )
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(result["source_kind"], "local_repository")
        self.assertFalse(result["offline_cache_verified"])
        self.assertIsNone(result["index_url"])

    def test_local_built_archive_is_checked_and_consumed_without_changing_release_assets(self):
        before = {file.name: file.read_bytes() for file in self.bundle_directory.iterdir()}
        with (
            patch("tools.cache_bundle.urlopen", side_effect=AssertionError("network used")),
            patch("tools.verify_consumer.subprocess.run", side_effect=self.native_process),
        ):
            result = verify_consumer(
                self.definition,
                self.triple,
                bundle_directory=self.bundle_directory,
                consumer_executable=self.consumer,
            )
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(result["source_kind"], "local_bundle")
        self.assertEqual(result["bundle_sha256"], self.bundle_sha)
        self.assertEqual(result["native_runs"][0]["root_relative"], self.variant)
        self.assertFalse(result["offline_cache_verified"])
        self.assertEqual(
            {file.name: file.read_bytes() for file in self.bundle_directory.iterdir()}, before
        )

    def test_damaged_built_archive_stops_before_native_execution(self):
        (self.bundle_directory / self.asset_name).write_bytes(b"damaged archive")
        with (
            patch("tools.verify_consumer.subprocess.run") as run,
            self.assertRaisesRegex(CacheError, "bundle archive checksum mismatch"),
        ):
            verify_consumer(
                self.definition,
                self.triple,
                bundle_directory=self.bundle_directory,
                consumer_executable=self.consumer,
            )
        run.assert_not_called()

    def test_public_acquisition_uses_the_independently_saved_index_pin(self):
        with (
            patch(
                "tools.cache_bundle.urlopen",
                side_effect=lambda url, **_: io.BytesIO(self.responses[url]),
            ) as download,
            patch("tools.verify_consumer.subprocess.run", side_effect=self.native_process),
        ):
            result = self.verify(index_sha256=None, trusted_index=self.trusted_index)
        self.assertEqual(download.call_count, 2)
        self.assertEqual(result["index_sha256"], self.index_sha)
        self.assertTrue(result["offline_cache_verified"])

    def test_damaged_trusted_index_stops_before_public_acquisition(self):
        self.trusted_index.write_bytes(b"damaged trusted index")
        with (
            patch("tools.verify_consumer.provision") as provision,
            patch("tools.verify_consumer.subprocess.run") as run,
            self.assertRaisesRegex(ConsumerError, "trusted local index checksum mismatch"),
        ):
            self.verify(index_sha256=None, trusted_index=self.trusted_index)
        provision.assert_not_called()
        run.assert_not_called()

    def test_foreign_target_is_rejected_before_cache_or_process_access(self):
        self.definition["targets"][0]["platform"] = (
            "linux" if self.platform == "windows" else "windows"
        )
        with (
            patch("tools.verify_consumer.provision") as provision,
            patch("tools.verify_consumer.subprocess.run") as run,
            self.assertRaisesRegex(BundleError, "native target"),
        ):
            self.verify()
        provision.assert_not_called()
        run.assert_not_called()

    def test_fresh_cache_gate_never_deletes_an_existing_cache(self):
        self.cache.mkdir()
        keep = self.cache / "existing-receipt"
        keep.write_bytes(b"preserve")
        with (
            patch("tools.verify_consumer.provision") as provision,
            self.assertRaisesRegex(ConsumerError, "empty cache"),
        ):
            self.verify()
        provision.assert_not_called()
        self.assertEqual(keep.read_bytes(), b"preserve")

    def test_missing_bare_smoke_evidence_cannot_be_reported_as_success(self):
        def incomplete(command, **kwargs):
            completed = self.native_process(command, **kwargs)
            completed.stdout = completed.stdout.replace(
                "PHASE_BEGIN bare\nFIXTURE_NATIVE_OK", "PHASE_BEGIN bare\nwrong output"
            )
            return completed

        with (
            patch("tools.verify_consumer.subprocess.run", side_effect=incomplete),
            self.assertRaisesRegex(ConsumerError, "bare smoke output"),
        ):
            verify_consumer(
                self.definition,
                self.triple,
                repository=self.repository,
                consumer_executable=self.consumer,
            )

    def test_native_process_nonzero_exit_cannot_be_replaced_by_a_receipt(self):
        with (
            patch(
                "tools.verify_consumer.subprocess.run",
                side_effect=subprocess.CalledProcessError(
                    1, [str(self.consumer)], stderr="contract failed"
                ),
            ),
            self.assertRaisesRegex(ConsumerError, "native adapter consumer failed"),
        ):
            verify_consumer(
                self.definition,
                self.triple,
                repository=self.repository,
                consumer_executable=self.consumer,
            )

    def test_local_repository_tampering_is_detected_on_reread(self):
        def corrupt_after_launch(command, **kwargs):
            completed = self.native_process(command, **kwargs)
            (self.repository / self.executable).write_bytes(b"corrupted source cache")
            return completed

        with (
            patch("tools.verify_consumer.subprocess.run", side_effect=corrupt_after_launch),
            self.assertRaisesRegex(CacheError, "checksum mismatch"),
        ):
            verify_consumer(
                self.definition,
                self.triple,
                repository=self.repository,
                consumer_executable=self.consumer,
            )
        self.assertEqual(len(self.requests), 1)

    def test_receipt_cannot_bind_a_different_root_or_omit_native_phase_evidence(self):
        with patch("tools.verify_consumer.subprocess.run", side_effect=self.native_process):
            verify_consumer(
                self.definition,
                self.triple,
                repository=self.repository,
                consumer_executable=self.consumer,
            )
        request = self.requests[0]
        for output in ("", "VX_REZ_CONSUMER_RECEIPT []", "VX_REZ_CONSUMER_RECEIPT {}"):
            with self.subTest(output=output), self.assertRaises(ConsumerError):
                _check_process_output(output, "FIXTURE_NATIVE_OK", request)
        receipt = {
            "schema_version": 1,
            **{key: request[key] for key in ("tool", "version", "platform", "arch")},
            "selected_root": request["expected_root"],
            "executable": request["executable"],
            "sdk_version": "test-sdk",
            "environment_keys": ["PATH"],
            "launches": ["direct", "bare"],
        }
        phases = (
            "\n".join(
                [
                    "VX_REZ_CONSUMER_PHASE_BEGIN direct",
                    "FIXTURE_NATIVE_OK",
                    "VX_REZ_CONSUMER_PHASE_END direct",
                    "VX_REZ_CONSUMER_PHASE_BEGIN bare",
                    "FIXTURE_NATIVE_OK",
                    "VX_REZ_CONSUMER_PHASE_END bare",
                ]
            )
            + "\n"
        )
        output = phases + "VX_REZ_CONSUMER_RECEIPT " + json.dumps(receipt)
        self.assertEqual(_check_process_output(output, "FIXTURE_NATIVE_OK", request), receipt)
        for changed in (
            {"selected_root": "outside"},
            {"executable": "outside"},
            {"launches": ["direct"]},
        ):
            with (
                self.subTest(changed=changed),
                self.assertRaisesRegex(ConsumerError, "selected root and launches"),
            ):
                _check_process_output(
                    phases + "VX_REZ_CONSUMER_RECEIPT " + json.dumps(receipt | changed),
                    "FIXTURE_NATIVE_OK",
                    request,
                )
        with self.assertRaisesRegex(ConsumerError, "exactly one"):
            _check_process_output(
                output + "\nVX_REZ_CONSUMER_RECEIPT " + json.dumps(receipt),
                "FIXTURE_NATIVE_OK",
                request,
            )

    def test_recipe_package_definition_pin_is_checked_before_native_execution(self):
        self.definition["package"]["definition"]["sha256"] = "c" * 64
        with (
            patch("tools.verify_consumer.subprocess.run") as run,
            self.assertRaisesRegex(BundleError, "consumer package definition checksum mismatch"),
        ):
            verify_consumer(
                self.definition,
                self.triple,
                repository=self.repository,
                consumer_executable=self.consumer,
            )
        run.assert_not_called()

    def test_local_repository_mode_cannot_claim_an_offline_release_cache_gate(self):
        with self.assertRaisesRegex(ConsumerError, "cannot claim index or offline-cache"):
            verify_consumer(
                self.definition,
                self.triple,
                repository=self.repository,
                consumer_executable=self.consumer,
                offline=True,
            )


if __name__ == "__main__":
    unittest.main()
