# Sample A — bare binary package

A minimal, reproducible VX runtime package whose upstream payload is a **single
bare executable** (no archive). Mirrors the shape of a `witr`-style release.

## 1. Rez-native expression (the package a consumer resolves)

`package.py` — valid upstream rez, no VX-specific fields:

```python
name = "sample_bin"
version = "1.0.0"
description = "Minimal bare-binary pilot sample"

variants = [
    ["platform-windows", "arch-x86_64"],
]

build_command = "python {root}/build.py {install}"


def commands():
    env.PATH.prepend("{root}/payload/bin")
```

`build.py` — the fetch / verify / place strategy, which upstream rez has no
primitive for and therefore delegates to the build command:

```python
import hashlib
import os
import shutil
import urllib.request

URL = "https://example.invalid/sample_bin.exe"
SHA256 = "<upstream digest>"
INSTALL = os.environ["REZ_BUILD_INSTALL_PATH"]

# 1. Fetch
source = os.path.join(os.environ["REZ_BUILD_SOURCE_PATH"], "sample_bin.exe")
urllib.request.urlretrieve(URL, source)

# 2. Verify integrity — no home in the rez package spec
digest = hashlib.sha256(open(source, "rb").read()).hexdigest()
if digest != SHA256:
    raise SystemExit(f"sha256 mismatch: {digest} != {SHA256}")

# 3. Place under the variant's payload root
target = os.path.join(INSTALL, "payload", "bin", "sample_bin.exe")
os.makedirs(os.path.dirname(target), exist_ok=True)
shutil.copyfile(source, target)
os.chmod(target, 0o755)
```

Installed layout (identical under upstream rez and rez-next — verified, see §4):

```text
sample_bin/1.0.0/package.py
sample_bin/1.0.0/platform-windows/arch-x86_64/payload/bin/sample_bin.exe
```

## 2. VX private protocol → rez-native mapping

| VX concept (`recipe.json`) | rez-native expression | Maps? | Conflict |
|---|---|---|---|
| `tool`, `version` | `name`, `version` in `package.py` | **Yes** | — |
| `targets[].triple` etc. | `variants` matrix (`platform-*`, `arch-*`) | **Yes** | `triple` itself must not enter `package.py`: unknown attributes are silently dropped into `extra_fields` (rez-next#352). Keep it recipe-side. |
| `targets[].arch` / `platform` | `variants` entries | **Yes** | rez `arch` vocabulary is `x86_64` / `arm_64`; host `amd64` differs (rez-next#321, #324) |
| `payload.format: "binary"` | no rez primitive — `build.py` copies the file | **Build strategy** | Not a protocol extension; fetch/verify/place is exactly what `build_command` is for |
| `payload.mappings[].destination` | `build.py` writes relative to `REZ_BUILD_INSTALL_PATH` | **Yes** | VX uses N mappings + `payload/` layer; `binary_archive` only strips one prefix and installs to the variant root — in rez it is moot because `build.py` owns placement |
| `payload.mappings[].executable` | `os.chmod(0o755)` in `build.py` | **Yes** | — |
| `upstream.url` | fetched inside `build.py` | **Yes** | rez has no `rez/utils/download.py`; fetching is user-strategy territory |
| `upstream.sha256` | `hashlib` check inside `build.py` | **Build strategy** | **No spec home**: `grep -rn sha256 src/rez/` returns nothing. The digest exists only as build-strategy code, never as a package attribute. |
| `package.definition.source` / `.sha256` | the `package.py` file itself + recipe-side check | **Yes** | The recipe pin is a CI-side check on checked-in bytes; rez needs no equivalent |
| `tools` | `tools = ["sample_bin"]` | **Yes** | — |
| `runner` | `commands()` | **Yes** | — |
| `unsupported_targets` | — | **No** | rez has no "exclude a variant" primitive; keep recipe/CI-side (product ruling 2026-10-11) |
| `build_revision` | rez `revision` / `previous_revision` | **Partial** | release currently omits revision (rez-next#347); carried by publish-layer `provenance.json` meanwhile |
| `provenance.json`, `manifest.json`, `sha256sums.txt` | — | **No** | **Spec-layer gap.** Not package content: published beside the package per the 2026-10-11 ruling. Do not fold into the payload. |
| deterministic `.tar.zst` | — | **No** | **Spec-layer gap.** rez has no `SOURCE_DATE_EPOCH`, no mtime/uid/gid normalisation, no canonical archive format. Byte-identity is a publish-pipeline property, not a rez package property. |

## 3. Conflicts / unmappable points

1. **`sha256` has no home in the rez package spec.** `grep -rn "sha256" src/rez/`
   (excluding vendored code) returns zero hits. The digest can be enforced by
   `build.py` but can never be *declared* by the package, so a consumer cannot
   verify provenance without VX's publish-layer files.
2. **Deterministic archives are not a rez concept.** No `SOURCE_DATE_EPOCH`
   support (only present in `src/rez/vendor/distlib/`), no metadata
   normalisation. `timestamp` is `int(time.time())` at release time — metadata,
   not a reproducibility primitive.
3. **`rez build --install` regenerates `package.py` rather than copying it**
   (`src/rezplugins/package_repository/filesystem.py:1445-1451`,
   `dump_package_data`): comments, formatting and non-`*_commands` functions are
   lost. VX's "copy exactly, never generate a fallback" is the opposite
   behaviour.
4. **Build-command environment.** rez-next clears the sub-process environment and
   does not restore `PATH` (rez-next#336), so a `build_command` that shells out
   to an interpreter fails unless `PATH` is re-injected. Verified in §4.

## 4. Reproduction and verification

Baseline: upstream rez `master` (`3.4.0`), rez-next `74da028`.

```bash
# Rez-native layout contract, verified on rez-next:
rez-next-runtime installation-plan \
    --definition witr_package.py --platform windows --arch x86_64 --json
# => "variant_relative_path":"witr/0.3.4/platform-windows/arch-x86_64"
```

This matches upstream rez, where the non-hashed subpath is
`os.path.join(*variant_requires)` (`src/rez/package_resources.py:493-522`,
assembled at `src/rezplugins/build_process/local.py:164-166`). **The single
precondition is `hashed_variants = False`**; with hashing on, the directory
becomes a SHA-1 name and breaks the manifest path contract.

Build-system selection, verified against rez-next source:
`build_command` is checked **before** `build_system`
(`crates/rez-next-build/src/systems/mod.rs:157-168`), so
`build_system = "custom"` + `build_command` resolves to
`Custom("build_command")` and **does execute the command**
(`crates/rez-next-build/src/systems/custom.rs:142`). See `docs/pilot/FINDINGS.md`
— this corrects the stage-0 audit's rez-next#330.
