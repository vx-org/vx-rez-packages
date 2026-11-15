# Sample B — zip archive package

A minimal, reproducible VX runtime package whose upstream payload is a **zip
archive with a leading directory prefix** and **N mappings** into the payload
root. This exercises the two capabilities that `binary_archive` cannot express.

## 1. Rez-native expression (the package a consumer resolves)

`package.py` — valid upstream rez, no VX-specific fields:

```python
name = "sample_zip"
version = "1.0.0"
description = "Minimal zip-archive pilot sample"

variants = [
    ["platform-windows", "arch-x86_64"],
    ["platform-linux", "arch-x86_64"],
]

build_command = "python {root}/build.py {install}"


def commands():
    env.PATH.prepend("{root}/payload/bin")
```

`build.py` — fetch, verify, strip the prefix, and apply N mappings:

```python
import hashlib
import os
import shutil
import urllib.request
import zipfile

URL = "https://example.invalid/sample_zip-1.0.0-windows-x86_64.zip"
SHA256 = "<upstream digest>"
INSTALL = os.environ["REZ_BUILD_INSTALL_PATH"]

# 1. Fetch
archive = os.path.join(os.environ["REZ_BUILD_SOURCE_PATH"], "payload.zip")
urllib.request.urlretrieve(URL, archive)

# 2. Verify integrity — no home in the rez package spec
digest = hashlib.sha256(open(archive, "rb").read()).hexdigest()
if digest != SHA256:
    raise SystemExit(f"sha256 mismatch: {digest} != {SHA256}")

# 3. Extract, strip the leading prefix, and apply N mappings
#    VX recipe (three mappings, each independently executable-flagged):
#      sample_zip-1.0.0/bin/sample_zip.exe  -> payload/bin/sample_zip.exe  (executable)
#      sample_zip-1.0.0/lib/*               -> payload/lib/
#      sample_zip-1.0.0/share/doc/*         -> payload/share/doc/
PREFIX = "sample_zip-1.0.0/"
MAPPINGS = [
    ("bin/sample_zip.exe", "payload/bin/sample_zip.exe", True),
    ("lib", "payload/lib", False),
    ("share/doc", "payload/share/doc", False),
]

with zipfile.ZipFile(archive) as zf:
    zf.extractall(os.environ["REZ_BUILD_SOURCE_PATH"] + "/extracted")

extracted = os.path.join(os.environ["REZ_BUILD_SOURCE_PATH"], "extracted", PREFIX)
for source, destination, executable in MAPPINGS:
    source_path = os.path.join(extracted, source)
    target_path = os.path.join(INSTALL, destination)
    if os.path.isdir(source_path):
        shutil.copytree(source_path, target_path, dirs_exist_ok=True)
    else:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        shutil.copyfile(source_path, target_path)
    if executable:
        os.chmod(target_path, 0o755)
```

Installed layout (one directory per variant):

```text
sample_zip/1.0.0/package.py
sample_zip/1.0.0/platform-windows/arch-x86_64/payload/bin/sample_zip.exe
sample_zip/1.0.0/platform-windows/arch-x86_64/payload/lib/...
sample_zip/1.0.0/platform-windows/arch-x86_64/payload/share/doc/...
sample_zip/1.0.0/platform-linux/arch-x86_64/payload/bin/sample_zip
```

## 2. VX private protocol → rez-native mapping

| VX concept (`recipe.json`) | rez-native expression | Maps? | Conflict |
|---|---|---|---|
| `tool`, `version` | `name`, `version` in `package.py` | **Yes** | — |
| multi-platform `targets[]` | `variants` matrix | **Yes** | Same as Sample A; `triple` stays recipe-side (#352) |
| `payload.format: "zip"` | `zipfile` inside `build.py` | **Build strategy** | Upstream rez has no archive build system at all; `binary_archive` is a rez-next extension with zero hits upstream |
| `payload.mappings[]` (N entries) | explicit copies in `build.py` | **Yes** | `binary_archive` strips **one** prefix and installs to the **variant root**, not a `payload/` layer, and has no mapping list (`crates/rez-next-build/src/systems/binary_archive.rs:131`). Moot under rez: `build.py` owns placement. |
| `payload.mappings[].executable` | `os.chmod(0o755)` | **Yes** | — |
| `payload.decoder` | — | **No** | VX-only concern (`py7zr` vs `native-7zip`); rez has no equivalent concept because it has no archive primitive |
| `upstream.sha256` | `hashlib` in `build.py` | **Build strategy** | **Spec-layer gap** — see Sample A §3.1 |
| `payload.format` values `tar` / `tar.zst` / `7z` | stdlib / `py7zr` in `build.py` | **Yes (under rez)** | Under rez-next `binary_archive` only accepts `.zip` / `.tar.gz` / `.tgz` (`binary_archive.rs:241-251`) — irrelevant once placement moves to `build.py` |
| per-variant smoke test | rez `tests` stanza | **Partial** | rez `tests` supports `command` / `requires` / `run_on` / `on_variants` only — **no expected-output assertion and no timeout** (`src/rez/package_resources.py:101-121`). VX `smoke_test.expect` and `.timeout_seconds` are spec-layer gaps. |
| `provenance.json`, `manifest.json`, `sha256sums.txt` | — | **No** | **Spec-layer gap** — published beside the package, never inside it |

## 3. Conflicts / unmappable points

1. **`sha256` has no home in the rez package spec** (`grep -rn sha256 src/rez/`
   → zero hits outside vendored code). Build-strategy only.
2. **Deterministic archives are not a rez concept** — no `SOURCE_DATE_EPOCH`, no
   mtime/uid/gid normalisation, no canonical archive format. Determinism is a
   publish-pipeline property; `rez build` only produces the payload.
3. **`tests` cannot assert output or bound runtime.** The schema accepts only
   `command` / `requires` / `run_on` / `on_variants`. VX's `smoke_test.expect`
   (assert on stdout) and `smoke_test.timeout_seconds` have no rez equivalent —
   two narrow spec-layer gaps.
4. **`rez build --install` regenerates rather than copies `package.py`**
   (`filesystem.py:1445-1451`), losing comments, formatting and non-`*_commands`
   functions — opposite to VX's byte-exact copy rule.
5. **Build-command environment** — rez-next clears the sub-process env and does
   not restore `PATH` (rez-next#336). Verified; see FINDINGS.md.

## 4. Reproduction and verification

Baseline: upstream rez `master` (`3.4.0`), rez-next `74da028`.

Upstream rez selects the `custom` build system whenever `build_command` is set,
*before* consulting `build_system` (`src/rez/build_system.py:62-63`), and
`is_valid_root` for `custom` just tests that `build_command is not None`
(`src/rezplugins/build_system/custom.py:61-70`). Every upstream build fixture
uses exactly this spelling — e.g. `src/rez/data/tests/builds/packages/foo/1.0.0/package.py:17`:

```python
build_command = "python {root}/build.py {install}"
```

Expansions available to the command (`src/rezplugins/build_system/custom.py:33-48`)
are `root`, `install`, `build_path`, `install_path`, `name`, `variant_index`,
`version`. rez-next implements the same set
(`crates/rez-next-build/src/systems/custom.rs:245-273`) — note `{variant_index}`
is expanded to the empty string there, whereas upstream supplies the real index.

`build_system`, `build_command`, `preprocess` and `pre_build_commands` are
stripped at install time (`src/rez/package_resources.py:42-48`,
`package_build_only_keys`), so build strategy never leaks into the published
package — the mechanism that keeps VX policy out of the rez package contract.
