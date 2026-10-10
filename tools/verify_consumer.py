"""Verify native public-adapter activation, then re-read the verified source offline."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

import jsonschema
import zstandard

from tools.build_bundle import (
    BundleError,
    _assert_native_target,
    _safe_relative,
    _select_target,
    _verify_sha256,
    load_definition,
    validate_definition,
)
from tools.cache_bundle import (
    CacheError,
    _digest,
    _relative,
    _verify_repository,
    materialize_archive,
    provision,
)
from tools.generate_index import _parse_checksum

RECEIPT_PREFIX = "VX_REZ_CONSUMER_RECEIPT "
PHASE_PREFIX = "VX_REZ_CONSUMER_PHASE_"


class ConsumerError(ValueError):
    """A consumer did not prove its native activation and execution contract."""


def _selection(definition: dict, target: dict) -> dict:
    return {
        "tool": definition["tool"],
        "version": definition["version"],
        "platform": target["platform"],
        "arch": target["arch"],
        "triple": target["triple"],
        "asset_name": (
            f"{definition['tool']}-{definition['version']}-{target['triple']}.rez.tar.zst"
        ),
        "package_root": f"{definition['tool']}/{definition['version']}",
    }


def _manifest(repository: Path, selected: dict) -> dict:
    _verify_repository(repository, selected)
    package = repository.joinpath(*_relative(selected["package_root"]).parts)
    return json.loads((package / "manifest.json").read_text(encoding="utf-8"))


def _check_process_output(stdout: str, expected: str, request: dict) -> dict:
    receipts = [
        line[len(RECEIPT_PREFIX) :]
        for line in stdout.splitlines()
        if line.startswith(RECEIPT_PREFIX)
    ]
    if len(receipts) != 1:
        raise ConsumerError("native consumer must emit exactly one successful receipt")
    receipt = json.loads(receipts[0])
    if (
        not isinstance(receipt, dict)
        or type(receipt.get("schema_version")) is not int
        or receipt["schema_version"] != 1
    ):
        raise ConsumerError("native consumer receipt schema is invalid")
    keys = receipt.get("environment_keys")
    if (
        not isinstance(receipt.get("sdk_version"), str)
        or not receipt["sdk_version"]
        or not isinstance(keys, list)
        or not all(isinstance(key, str) and key for key in keys)
        or len(keys) != len(set(keys))
    ):
        raise ConsumerError("native consumer receipt environment metadata is invalid")
    for key in ("tool", "version", "platform", "arch"):
        if receipt.get(key) != request[key]:
            raise ConsumerError(f"native consumer receipt does not match {key}")
    if (
        receipt.get("selected_root") != request["expected_root"]
        or receipt.get("executable") != request["executable"]
        or receipt.get("launches") != ["direct", "bare"]
    ):
        raise ConsumerError("native consumer receipt does not match its selected root and launches")
    if (
        request["expected_sdk_version"] is not None
        and receipt.get("sdk_version") != request["expected_sdk_version"]
    ):
        raise ConsumerError("native consumer receipt does not match its SDK pin")
    lines = stdout.splitlines()
    boundaries = [line for line in lines if line.startswith(PHASE_PREFIX)]
    expected_boundaries = [
        "VX_REZ_CONSUMER_PHASE_BEGIN direct",
        "VX_REZ_CONSUMER_PHASE_END direct",
        "VX_REZ_CONSUMER_PHASE_BEGIN bare",
        "VX_REZ_CONSUMER_PHASE_END bare",
    ]
    if boundaries != expected_boundaries:
        raise ConsumerError("native consumer smoke phase boundaries are invalid")
    for phase in ("direct", "bare"):
        start = lines.index(f"VX_REZ_CONSUMER_PHASE_BEGIN {phase}")
        end = lines.index(f"VX_REZ_CONSUMER_PHASE_END {phase}")
        if expected not in "\n".join(lines[start + 1 : end]):
            raise ConsumerError(f"native {phase} smoke output does not match the recipe")
    return receipt


def _run_native(
    repository: Path,
    selected: dict,
    definition: dict,
    target: dict,
    consumer_executable: Path,
    expected_environment: dict[str, str] | None,
    expected_sdk_version: str | None,
) -> dict:
    manifest = _manifest(repository, selected)
    package = repository.joinpath(*_relative(selected["package_root"]).parts)
    _verify_sha256(
        package / "package.py",
        definition["package"]["definition"]["sha256"],
        "consumer package definition",
    )
    if (
        manifest["upstream"]["archive_url"] != target["upstream"]["url"]
        or manifest["upstream"]["archive_sha256"] != target["upstream"]["sha256"]
    ):
        raise ConsumerError("bundle upstream payload does not match the native recipe pin")
    with tempfile.TemporaryDirectory(prefix="vx-rez-consumer-") as temporary:
        working = Path(temporary).resolve()
        isolated = working / "repository"
        shutil.copytree(repository, isolated, symlinks=True)
        _verify_repository(isolated, selected)
        payload = isolated.joinpath(*_relative(manifest["payload_root"]).parts)
        variant = payload.parent
        substitutions = {
            "root": str(variant),
            "version": definition["version"],
            "exe": ".exe" if target["platform"] == "windows" else "",
        }
        smoke = target.get("smoke_test", definition["package"]["smoke_test"])
        command = [argument.format_map(substitutions) for argument in smoke["command"]]
        executable = Path(command[0])
        if not executable.is_absolute() or not executable.is_file() or executable.is_symlink():
            raise ConsumerError("native smoke must name an absolute regular payload executable")
        try:
            executable.resolve(strict=True).relative_to(payload.resolve())
        except (OSError, ValueError) as error:
            raise ConsumerError("native smoke executable leaves the selected payload") from error
        if expected_environment is None:
            entries = [
                str(variant / _safe_relative(entry))
                for entry in definition["package"]["path_entries"]
            ]
            environment = {"PATH": os.pathsep.join(entries)}
        else:
            if not isinstance(expected_environment, dict) or not all(
                isinstance(key, str) and key and isinstance(value, str)
                for key, value in expected_environment.items()
            ):
                raise ConsumerError("expected environment must be a string-to-string object")
            environment = {
                key: value.format_map(substitutions) for key, value in expected_environment.items()
            }
        # Core exports metadata for the runtime and the two explicit target packages.
        for name, version, root in (
            (definition["tool"], definition["version"], variant),
            ("platform", target["platform"], isolated / "platform" / target["platform"]),
            ("arch", target["arch"], isolated / "arch" / target["arch"]),
        ):
            environment.setdefault(f"{name.upper()}_ROOT", str(root))
            environment.setdefault(f"{name.upper()}_VERSION", version)
        request = {
            "schema_version": 1,
            "repository": str(isolated),
            "tool": definition["tool"],
            "version": definition["version"],
            "platform": target["platform"],
            "arch": target["arch"],
            "expected_root": str(variant),
            "payload_root": str(payload),
            "executable": str(executable),
            "command": command,
            "expected_environment": environment,
            "expected_sdk_version": expected_sdk_version,
        }
        request_path = working / "consumer-request.json"
        request_path.write_text(json.dumps(request), encoding="utf-8")
        parent = os.environ.copy()
        parent["VX_CONSUMER_PARENT_SENTINEL"] = "must-not-enter-resolved-environment"
        try:
            completed = subprocess.run(
                [str(consumer_executable), str(request_path)],
                cwd=variant,
                env=parent,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
                shell=False,
                timeout=2 * smoke.get("timeout_seconds", 60) + 60,
            )
        except (OSError, subprocess.SubprocessError) as error:
            detail = (getattr(error, "stderr", "") or "").strip()[:2000]
            raise ConsumerError(f"native adapter consumer failed: {error}; {detail}") from error
        receipt = _check_process_output(
            completed.stdout, smoke["expect"].format_map(substitutions), request
        )
        return {
            "root_relative": variant.relative_to(isolated).as_posix(),
            "executable_relative": executable.relative_to(isolated).as_posix(),
            "sdk_version": receipt["sdk_version"],
            "environment_keys": receipt["environment_keys"],
            "launches": receipt["launches"],
        }


def verify_consumer(
    definition: dict,
    triple: str,
    *,
    consumer_executable: Path,
    repository: Path | None = None,
    bundle_directory: Path | None = None,
    index_url: str | None = None,
    index_sha256: str | None = None,
    trusted_index: Path | None = None,
    cache: Path | None = None,
    offline: bool = False,
    require_empty_cache: bool = False,
    expected_environment: dict[str, str] | None = None,
    expected_sdk_version: str | None = None,
) -> dict:
    """Prove native activation twice; public index mode additionally proves an offline cache hit."""
    validate_definition(definition)
    target = _select_target(definition, triple)
    _assert_native_target(target)
    selected = _selection(definition, target)
    consumer_executable = consumer_executable.resolve(strict=True)
    if not consumer_executable.is_file():
        raise ConsumerError("consumer executable must be an explicit regular file")
    if expected_sdk_version is not None and not expected_sdk_version:
        raise ConsumerError("expected SDK version cannot be empty")
    if bundle_directory is not None:
        if (
            any(
                value is not None
                for value in (repository, index_url, index_sha256, trusted_index, cache)
            )
            or offline
            or require_empty_cache
        ):
            raise ConsumerError("local bundle mode cannot claim index or offline-cache acquisition")
        archive = bundle_directory / selected["asset_name"]
        companion = archive.with_name(archive.name + ".sha256")
        digest = _parse_checksum(companion.read_text(encoding="utf-8"), archive.name)
        with tempfile.TemporaryDirectory(prefix="vx-rez-built-bundle-") as temporary:
            extracted = materialize_archive(
                archive, digest, Path(temporary) / "repository", selected
            )
            receipt = verify_consumer(
                definition,
                triple,
                consumer_executable=consumer_executable,
                repository=extracted,
                expected_environment=expected_environment,
                expected_sdk_version=expected_sdk_version,
            )
        return receipt | {"source_kind": "local_bundle", "bundle_sha256": digest}
    public_mode = repository is None
    if public_mode:
        if trusted_index is not None:
            if index_sha256 is not None:
                raise ConsumerError("use either an index checksum or a trusted local index")
            companion = trusted_index.with_name(trusted_index.name + ".sha256")
            index_sha256 = _parse_checksum(
                companion.read_text(encoding="utf-8"), trusted_index.name
            )
            if _digest(trusted_index) != index_sha256:
                raise ConsumerError("trusted local index checksum mismatch")
        if index_url is None or index_sha256 is None or cache is None:
            raise ConsumerError("index URL, checksum and cache are required together")
        cache = cache.resolve()
        cache_empty = not cache.exists() or not any(cache.iterdir())
        if require_empty_cache and (not cache_empty or offline):
            raise ConsumerError("fresh acquisition requires an empty cache and online provisioning")
        repository = provision(
            index_url,
            index_sha256,
            cache,
            tool=selected["tool"],
            version=selected["version"],
            platform=selected["platform"],
            arch=selected["arch"],
            offline=offline,
        )
    else:
        if (
            any(value is not None for value in (index_url, index_sha256, trusted_index, cache))
            or offline
            or require_empty_cache
        ):
            raise ConsumerError(
                "local repository mode cannot claim index or offline-cache acquisition"
            )
        cache_empty = None
    repository = repository.resolve(strict=True)
    first = _run_native(
        repository,
        selected,
        definition,
        target,
        consumer_executable,
        expected_environment,
        expected_sdk_version,
    )
    if public_mode:
        reread = provision(
            index_url,
            index_sha256,
            cache,
            tool=selected["tool"],
            version=selected["version"],
            platform=selected["platform"],
            arch=selected["arch"],
            offline=True,
        )
        if reread.resolve() != repository:
            raise ConsumerError("offline cache returned a different repository")
    else:
        _verify_repository(repository, selected)
    second = _run_native(
        repository,
        selected,
        definition,
        target,
        consumer_executable,
        expected_environment,
        expected_sdk_version,
    )
    if first != second:
        raise ConsumerError("repeated native consumer results differ")
    return {
        "schema_version": 1,
        "tool": definition["tool"],
        "version": definition["version"],
        "platform": target["platform"],
        "arch": target["arch"],
        "triple": triple,
        "source_kind": "pinned_release_index" if public_mode else "local_repository",
        "index_url": index_url,
        "index_sha256": index_sha256,
        "initial_cache_empty": cache_empty,
        "offline_cache_verified": public_mode,
        "repository_reread_verified": True,
        "native_runs": [first, second],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", type=Path, required=True)
    parser.add_argument("--triple", required=True)
    parser.add_argument("--consumer-executable", type=Path, required=True)
    parser.add_argument("--repository", type=Path)
    parser.add_argument("--bundle-dir", dest="bundle_directory", type=Path)
    parser.add_argument("--index-url")
    parser.add_argument("--index-sha256")
    parser.add_argument("--trusted-index", type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--require-empty-cache", action="store_true")
    parser.add_argument("--expected-environment", type=Path)
    parser.add_argument("--expected-sdk-version")
    parser.add_argument("--output", type=Path)
    args = vars(parser.parse_args())
    output = args.pop("output")
    try:
        args["definition"] = load_definition(args["definition"])
        expectations = args["expected_environment"]
        args["expected_environment"] = (
            json.loads(expectations.read_text(encoding="utf-8")) if expectations else None
        )
        receipt = verify_consumer(**args)
        document = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(document, encoding="utf-8")
        print(document, end="")
    except (
        BundleError,
        CacheError,
        ConsumerError,
        OSError,
        ValueError,
        KeyError,
        jsonschema.ValidationError,
        tarfile.TarError,
        zstandard.ZstdError,
    ) as error:
        parser.exit(1, f"native consumer verification failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
