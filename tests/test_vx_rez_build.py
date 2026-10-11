from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from tools import build_bundle
from tools.vx_rez_build import builder
from tools.vx_rez_build.builder import (
    BuildError,
    build_variant,
    host_triple,
    validate_package_definition,
)
from tools.vx_rez_build.cli import main as cli_main

TRIPLE = "x86_64-pc-windows-msvc"


def installation_plan(package, definition, target, sdk_executable, repositories) -> dict:
    package = f"{definition['tool']}/{definition['version']}"
    return {
        "schema_version": 1,
        "name": definition["tool"],
        "version": definition["version"],
        "platform": "windows",
        "arch": "x86_64",
        "variant_index": 2,
        "variant_requirements": ["platform-windows", "arch-x86_64"],
        "package_relative_path": package,
        "variant_relative_path": package + "/platform-windows/arch-x86_64",
    }


def package_source(
    build_system: str | None = "build.py", *, name="fixture", version="1.2.3"
) -> bytes:
    lines = [f"name = {name!r}", f"version = {version!r}", "tools = ['fixture']"]
    if build_system is not None:
        lines.append(f"build_system = {build_system!r}")
    return ("\n".join(lines) + "\n").encode()


def digest(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def recipe(directory: Path) -> dict:
    """A schema-valid recipe whose package.py is pinned by digest."""
    package_file = directory / "package.py"
    package_file.write_bytes(package_source())
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
            "definition": {"source": "package.py", "sha256": digest(package_file)},
            "description": "Wrapper contract test runtime",
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
        "release_assets": [],
        "targets": [
            {
                "triple": TRIPLE,
                "platform": "windows",
                "arch": "x86_64",
                "runner": "windows-2025",
                "status": "supported",
                "upstream": {
                    "url": "https://example.invalid/payload",
                    "sha256": "3" * 64,
                },
                "payload": {
                    "format": "binary",
                    "mappings": [
                        {"source": ".", "destination": "bin/fixture.exe", "executable": True}
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


class ValidatePackageDefinitionTests(unittest.TestCase):
    def test_accepts_named_build_script(self):
        validate_package_definition(package_source("build.py"))

    def test_rejects_custom_build_system(self):
        """rez-next resolves 'custom' to a copy-only build; the script never runs."""
        with self.assertRaisesRegex(BuildError, "copy-only build"):
            validate_package_definition(package_source("custom"))

    def test_rejects_missing_build_system(self):
        with self.assertRaisesRegex(BuildError, "must declare build_system"):
            validate_package_definition(package_source(None))

    def test_rejects_non_literal_build_system(self):
        source = b"name = 'spike'\nversion = '0.0.1'\nbuild_system = some_call()\n"
        with self.assertRaisesRegex(BuildError, "literal string"):
            validate_package_definition(source)

    def test_rejects_invalid_syntax(self):
        with self.assertRaisesRegex(BuildError, "invalid Python syntax"):
            validate_package_definition(b"name =\n")


class HostTripleTests(unittest.TestCase):
    def test_translates_amd64_to_x86_64(self):
        with (
            patch.object(builder.host_platform, "machine", return_value="AMD64"),
            patch.object(builder.host_platform, "system", return_value="Windows"),
        ):
            self.assertEqual(host_triple(), ("windows", "x86_64"))


class BuildVariantTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.recipe_directory = self.root / "recipe"
        self.recipe_directory.mkdir()
        self.definition = recipe(self.recipe_directory)
        (self.recipe_directory / "recipe.json").write_text(
            json.dumps(self.definition), encoding="utf-8"
        )
        self.output = self.root / "out"

    def _patch(self):
        return (
            patch.object(builder, "_run_rez_build"),
            patch.object(builder.build_bundle, "_installation_plan", side_effect=installation_plan),
            patch.object(builder, "_assert_native_target"),
        )

    def test_builds_variant_and_asserts_payload(self):
        def fake_rez(**kwargs):
            repository = kwargs["repository"]
            variant = repository / "fixture" / "1.2.3" / "platform-windows" / "arch-x86_64"
            (variant / "payload" / "bin").mkdir(parents=True)
            (variant / "payload" / "bin" / "fixture.exe").write_bytes(b"binary")

        with self._patch()[0] as run, self._patch()[1], self._patch()[2]:
            run.side_effect = fake_rez
            result = build_variant(
                self.definition, TRIPLE, self.output, metadata_directory=self.recipe_directory
            )

        self.assertTrue(result.is_dir())
        package_py = result / "fixture" / "1.2.3" / "package.py"
        self.assertEqual(package_py.read_bytes(), package_source())
        self.assertTrue((result / "platform" / "windows" / "package.py").is_file())
        self.assertTrue((result / "arch" / "x86_64" / "package.py").is_file())
        payload = result / "fixture" / "1.2.3" / "platform-windows" / "arch-x86_64" / "payload"
        self.assertTrue((payload / "bin" / "fixture.exe").is_file())

    def test_rejects_empty_payload(self):
        def empty_payload(**kwargs):
            repository = kwargs["repository"]
            variant = repository / "fixture" / "1.2.3" / "platform-windows" / "arch-x86_64"
            (variant / "payload").mkdir(parents=True)

        with self._patch()[0] as run, self._patch()[1], self._patch()[2]:
            run.side_effect = empty_payload
            with self.assertRaisesRegex(BuildError, "empty payload"):
                build_variant(
                    self.definition, TRIPLE, self.output, metadata_directory=self.recipe_directory
                )

    def test_rejects_missing_payload_directory(self):
        def noop(**kwargs):
            return None

        with self._patch()[0] as run, self._patch()[1], self._patch()[2]:
            run.side_effect = noop
            with self.assertRaisesRegex(BuildError, "no payload directory"):
                build_variant(
                    self.definition, TRIPLE, self.output, metadata_directory=self.recipe_directory
                )

    def test_rejects_undeclared_triple(self):
        with self.assertRaisesRegex(BuildError, "not declared"):
            build_variant(self.definition, "aarch64-unknown-linux-gnu", self.output)

    def test_rejects_unsupported_triple(self):
        with self.assertRaisesRegex(BuildError, "unsupported"):
            build_variant(self.definition, "i686-pc-windows-msvc", self.output)

    def test_rejects_custom_build_system_in_pinned_definition(self):
        # Build the recipe first so its digest pins the custom bytes, then write
        # those exact bytes back so the pin validates and the build system is
        # what fails.
        definition = recipe(self.recipe_directory)
        custom = package_source("custom")
        (self.recipe_directory / "package.py").write_bytes(custom)
        definition["package"]["definition"]["sha256"] = digest(self.recipe_directory / "package.py")
        patches = [
            *self._patch()[0:2],
            patch.object(builder, "_assert_native_target"),
            self.assertRaisesRegex(BuildError, "copy-only build"),
        ]
        with ExitStack() as stack:
            for item in patches:
                stack.enter_context(item)
            build_variant(definition, TRIPLE, self.output, metadata_directory=self.recipe_directory)


class NativeTargetTests(unittest.TestCase):
    def test_refuses_cross_build(self):
        target = {"platform": "linux", "arch": "x86_64"}
        with (
            patch.object(builder, "host_triple", return_value=("windows", "x86_64")),
            self.assertRaisesRegex(BuildError, "native target"),
        ):
            builder._assert_native_target(target)

    def test_accepts_matching_target(self):
        target = {"platform": "windows", "arch": "x86_64"}
        with patch.object(builder, "host_triple", return_value=("windows", "x86_64")):
            builder._assert_native_target(target)


class EnvironmentContractTests(unittest.TestCase):
    def test_sets_path_and_target_variables(self):
        environment = builder._build_environment(
            base={"PATH": "/usr/bin"},
            bootstrap_repository=Path("/bootstrap"),
            target={"platform": "windows", "arch": "x86_64"},
            triple=TRIPLE,
            recipe_path=Path("/recipe/recipe.json"),
            extra_paths=[Path("/rez/bin")],
        )
        entries = environment["PATH"].split(os.pathsep)
        self.assertEqual(entries[0], str(Path("/rez/bin")))
        self.assertIn("/usr/bin", entries)
        self.assertTrue(entries)
        self.assertEqual(environment["REZ_BUILD_TARGET_PLATFORM"], "windows")
        self.assertEqual(environment["REZ_BUILD_TARGET_ARCH"], "x86_64")
        self.assertEqual(environment["REZ_BUILD_TARGET_OS"], "windows")
        self.assertEqual(environment["REZ_PACKAGES_PATH"], str(Path("/bootstrap")))
        self.assertEqual(environment["VX_BUILD_TRIPLE"], TRIPLE)
        self.assertTrue(os.path.isabs(environment["VX_BUILD_RECIPE"]))

    def test_target_os_mapping(self):
        self.assertEqual(builder._target_os("osx"), "macos")
        self.assertEqual(builder._target_os("linux"), "linux")


class RezExecutionTests(unittest.TestCase):
    def test_missing_rez_executable_is_reported(self):
        environment = dict(os.environ)
        environment.pop("VX_REZ_EXECUTABLE", None)
        with (
            patch.dict(os.environ, environment, clear=True),
            patch.object(builder.shutil, "which", return_value=None),
            self.assertRaisesRegex(BuildError, "rez-next executable is required"),
        ):
            builder._resolve_rez_executable()

    def test_prefers_rez_next_over_a_legacy_rez_on_path(self):
        """A pip-installed rez 3.x shadows the name; rez-next must win."""
        environment = dict(os.environ)
        environment.pop("VX_REZ_EXECUTABLE", None)
        resolved = {"rez": "/usr/bin/rez", "rez-next": "/usr/bin/rez-next"}
        with (
            patch.dict(os.environ, environment, clear=True),
            patch.object(builder.shutil, "which", side_effect=resolved.get),
        ):
            self.assertEqual(builder._resolve_rez_executable(), Path("/usr/bin/rez-next"))

    def test_falls_back_to_rez_when_rez_next_is_absent(self):
        environment = dict(os.environ)
        environment.pop("VX_REZ_EXECUTABLE", None)
        resolved = {"rez": "/usr/bin/rez"}
        with (
            patch.dict(os.environ, environment, clear=True),
            patch.object(builder.shutil, "which", side_effect=resolved.get),
        ):
            self.assertEqual(builder._resolve_rez_executable(), Path("/usr/bin/rez"))

    def test_vx_rez_executable_overrides_path_lookup(self):
        with (
            patch.dict(os.environ, {"VX_REZ_EXECUTABLE": "/opt/rez-next"}, clear=True),
            patch.object(builder.shutil, "which", return_value="/usr/bin/rez-next"),
        ):
            self.assertEqual(builder._resolve_rez_executable(), Path("/opt/rez-next"))

    def test_failure_surfaces_exit_code(self):
        with (
            patch.object(builder, "_resolve_rez_executable", return_value=Path("/bin/rez")),
            patch.object(
                builder.subprocess,
                "run",
                side_effect=builder.subprocess.CalledProcessError(2, "rez", stderr="boom"),
            ),
            self.assertRaisesRegex(BuildError, "exit code 2: boom"),
        ):
            builder._run_rez_build(
                source=Path("/src"),
                repository=Path("/repo"),
                bootstrap_repository=Path("/boot"),
                package_source=Path("/src/package.py"),
                target={"platform": "windows", "arch": "x86_64"},
                triple=TRIPLE,
                recipe_path=Path("/src/recipe.json"),
                rez_executable=None,
            )


class CommandLineTests(unittest.TestCase):
    def test_cli_builds_and_prints_repository(self):
        from tools.vx_rez_build import cli

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            definition = recipe(directory)
            with (
                patch.object(cli, "load_definition", return_value=definition) as load,
                patch.object(cli, "build_variant", return_value=Path("/out/spike")) as build,
            ):
                exit_code = cli_main(
                    ["--definition", "recipe.json", "--triple", TRIPLE, "--output-dir", "out"]
                )
        self.assertEqual(exit_code, 0)
        load.assert_called_once()
        build.assert_called_once()

    def test_cli_reports_errors(self):
        from tools.vx_rez_build import cli

        with (
            patch.object(cli, "load_definition", side_effect=BuildError("bad recipe")),
            self.assertRaises(SystemExit) as raised,
        ):
            cli_main(["--definition", "r.json", "--triple", TRIPLE, "--output-dir", "out"])
        self.assertIn("bad recipe", str(raised.exception))


class PackStageEquivalenceTests(unittest.TestCase):
    def test_extracted_pack_stage_matches_legacy_private_helpers(self):
        """The extracted module must preserve the published deterministic rules."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            (repository / "payload" / "bin").mkdir(parents=True)
            (repository / "payload" / "bin" / "spike").write_bytes(b"binary")
            (repository / "package.py").write_bytes(package_source())

            legacy = repository / "legacy-sha256sums.txt"
            shared = repository / "shared-sha256sums.txt"
            build_bundle._write_repository_checksums(repository, legacy)
            from tools import pack_stage

            pack_stage.write_repository_checksums(repository, shared)
            # Both exclude their own destination only; content hashes align.
            legacy_lines = {
                line.split("  ", 1)[1]: line.split("  ", 1)[0]
                for line in legacy.read_text().splitlines()
                if line
            }
            shared_lines = {
                line.split("  ", 1)[1]: line.split("  ", 1)[0]
                for line in shared.read_text().splitlines()
                if line
            }
            expected = {
                "payload/bin/spike": legacy_lines["payload/bin/spike"],
                "package.py": legacy_lines["package.py"],
            }
            for name, digest in expected.items():
                self.assertEqual(shared_lines[name], digest, name)

            legacy_archive = root / "legacy.tar.zst"
            shared_archive = root / "shared.tar.zst"
            build_bundle._write_reproducible_tar_zstd(
                repository, legacy_archive, "2026-10-11", executable_paths=set()
            )
            pack_stage.write_reproducible_tar_zstd(
                repository, shared_archive, "2026-10-11", executable_paths=set()
            )
            self.assertEqual(legacy_archive.read_bytes(), shared_archive.read_bytes())


if __name__ == "__main__":
    unittest.main()
