# build.py contract

Status: **proposed**. The mechanism is proven — a real `rez build` run on
rez-next 0.3.10 produced
`<prefix>/spike/0.0.1/platform-windows/arch-x86_64/payload/bin/spike.txt`,
which is the layout VX already publishes. What is still proposed is the wrapper's
command surface and the environment additions it has to make. Backing evidence is
in [`spike-rez-build-feasibility.md`](spike-rez-build-feasibility.md); the `witr`
pilot remains to be run.

This contract governs how a VX Rez package builds itself. It does **not** change
what VX publishes: the `.rez.tar.zst` bundle, `index.json`, retained originals and
the four `schema_version: 1` schemas stay exactly as they are.

## The division of labour

| Layer | Owns | Changes? |
| ----- | ---- | -------- |
| `recipe.json` | declarative truth: targets, upstream URL + SHA-256, payload mappings, metadata files, smoke test | no |
| `build.py` | building **one** target's payload into the variant root | new |
| `vx build` | wrapper: pick the target, set the environment, call `rez build`, copy `package.py` | new |
| pack stage | deterministic `tar.zst`, `sha256sums.txt`, `manifest.json`, `provenance.json` | extracted from `tools/build_bundle.py` |
| `runtime-release.yml` | matrix, native smoke, index, publish, public-consumer verification | one step |

`recipe.json` stays the only place any fact is declared. `build.py` reads it; it
does not restate it. There is no second copy of a URL, a digest or a version.

## Declaring the build

`package.py` selects the build system by **file name**. Any value that rez-next
does not recognise as a built-in becomes `Custom(<that value>)`, which is exactly
what we want:

```python
name = "witr"
version = "0.3.4"
build_system = "build.py"
```

Two rules follow, and both are enforceable by test:

- **Never** write `build_system = "custom"`. rez-next resolves that to
  `Custom("default")`, which is a copy-only build — the script is silently never
  executed.
- The named file must sit at the package root, next to `package.py`.

`package.py` remains the pinned, hash-checked, AST-validated, never-executed
input it is today. Adding `build_system` is the only change to it.

## How the script is invoked

rez-next runs, with a cleared environment (see below):

```text
python -c <bootstrap> <build_plugins.py> <script> build
python -c <bootstrap> <build_plugins.py> <script> install
python -c <bootstrap> <build_plugins.py> <script> test
```

The bootstrap makes `rez_next.build_plugins` importable and then runs the script
with `runpy.run_path(script, run_name="__main__")`. So:

- `sys.argv` is `[script_path, "build" | "install" | "test"]`.
- Module-level code runs; no specific function is required. The `BuildPlugin`
  base class is the recommended shape:

  ```python
  from rez_next.build_plugins import BuildPlugin

  class Build(BuildPlugin):
      def install(self) -> None:
          ...

  if __name__ == "__main__":
      Build().run()
  ```

- **The script runs from a temporary copy, not from the package root.** rez-next
  copies the package into `%TEMP%/rez-core-build-cache/<name>-<version>-<pid>-<ns>/`
  and executes it there; `cwd`, `__file__` and `REZ_BUILD_SOURCE_PATH` all point
  at that copy. A `build.py` must therefore never resolve `recipe.json`, a
  license file or a patch relative to itself — take absolute paths from the
  environment instead.
- **Only the exit code crosses back.** Non-zero fails the build. Nothing checks
  that you wrote anything, so the pack stage must assert a non-empty payload.

## Environment contract

The child environment is cleared before the script environment is applied, so
every variable a `build.py` may rely on has to be named here. The wrapper sets
them; `build.py` reads them.

This is not defensive boilerplate. On Windows, a cleared child environment was
measured to contain `TEMP`, `TMP` and `SystemRoot` and **no `PATH` at all** — a
`build.py` that shells out to `7z`, `git`, `curl` or `tar` fails without an
explicit `PATH`.

| Variable | Set by | Meaning |
| -------- | ------ | ------- |
| `REZ_BUILD_INSTALL_PATH` | rez-next | the **variant root**. `build.py` writes `payload/` under it |
| `REZ_BUILD_SOURCE_PATH` | rez-next | **not** the package root — the temp build cache the script was copied into. Use `VX_BUILD_RECIPE`'s directory instead |
| `REZ_BUILD_PATH` | rez-next | scratch build directory |
| `REZ_BUILD_PACKAGE_NAME` / `_VERSION` | rez-next | package identity |
| `REZ_BUILD_VARIANT_INDEX` / `_REQUIRES` | rez-next | selected variant |
| `REZ_BUILD_TARGET_PLATFORM` / `_ARCH` / `_OS` | **`vx build`** | rez-next reads these but never sets them; left unset they silently default to the **host**, so the wrapper must derive them from the recipe target |
| `REZ_PACKAGES_PATH` | **`vx build`** | repository holding the sibling `platform/` and `arch/` system packages. `rez build` has **no** `--repository` flag, and without this the variant fails to resolve |
| `VX_BUILD_TRIPLE` | **`vx build`** | the recipe's `targets[].triple`, e.g. `x86_64-pc-windows-msvc` |
| `VX_BUILD_RECIPE` | **`vx build`** | **absolute** path to `recipe.json` — see the temp-copy caveat above |
| `PATH`, `TEMP`, `TMP`, `SystemRoot`, `WINDIR`, proxy variables | **`vx build`** | whatever the environment-clearing would otherwise strip. `PATH` is required, not optional |

Prefer `BuildContext.from_env()` over reading them directly; it supplies defaults
for the ones rez-next does not set — and those defaults are host values, so
confirm `target_platform` / `target_arch` really came from the wrapper before
trusting them.

Note the arch vocabulary mismatch: Rez reports the host arch as `amd64`, while
the package family VX uses is `arch-x86_64`. Translate explicitly; do not pass
`target_arch` through.

## What `build.py` must produce

Given `REZ_BUILD_INSTALL_PATH`, the script must leave:

```text
<install_path>/payload/...          the mapped payload for this one target
```

Everything else — `package.py`, `manifest.json`, `provenance.json`,
`sha256sums.txt`, the sibling `platform/` and `arch/` system packages, and the
archive itself — belongs to the wrapper and the pack stage, not to `build.py`.

`build.py` must additionally preserve three invariants that the published
contract depends on:

1. **No symlinks.** Copy symlink content, not links. `copy_tree_contents()` from
   `rez_next.build_plugins` already does this.
2. **Executable bits are declared, not inherited.** Set them explicitly from the
   recipe mapping's `executable` flag; do not trust the host filesystem.
3. **Verify before use.** Check the upstream SHA-256 before extracting, and
   reject archive members that escape the extraction root.

## Relationship with `recipe.json`

`recipe.json` is the input; `build.py` is the executor. Concretely:

- `targets[].upstream.url` and `.sha256` — what to fetch and what to verify.
- `targets[].payload.mappings[]` — where each source lands under `payload/`.
- `targets[].payload.format` — how to open the archive. `tar.zst` is **not**
  supported by `rez_next.build_plugins.extract_archive()` (zip/whl/tar.gz/tgz
  only), so a `tar.zst` recipe needs zstd handling in `build.py` or an upstream
  change. This is why `witr` is the pilot and `python` is not.
- `metadata[]` and `release_assets[]` — **not** `build.py`'s job. They are
  installed and retained by the wrapper and the pack stage.
- `package.smoke_test` — still executed by `runtime-release.yml` against the
  finished bundle. Unchanged.

Nothing is written back into `recipe.json`, and `recipe.json` is not regenerated
from `build.py`.

## What `vx build` does

```text
vx-rez-build --definition recipe.json --triple <triple> --output-dir <dir>
```

1. Load and validate `recipe.json` (existing validator, unchanged).
2. Select the target matching `--triple`; fail if the host does not match its
   `platform` / `arch`.
3. Resolve the variant through the SDK's `installation-plan`, exactly as
   `tools/build_bundle.py` does today. The layout stays SDK-owned; nothing infers
   it locally.
4. Materialise the sibling `platform/<p>/` and `arch/<a>/` system packages into a
   bootstrap repository and point `REZ_PACKAGES_PATH` at it. `rez build` cannot
   be given a repository on the command line.
5. Copy the pinned `package.py` byte-for-byte to `<name>/<version>/package.py`.
   The plain rez-next build path does not do this; only its release path does.
6. Set the environment contract — including `PATH`, the `REZ_BUILD_TARGET_*`
   triple and an absolute `VX_BUILD_RECIPE` — and run
   `rez build <source> --install --prefix <repository> --build-system build.py`.
7. Assert the payload is non-empty (guards the exit-code-only marshalling).
8. Hand the repository to the pack stage.

Steps 5 and 7 are the two places where the wrapper compensates for real
rez-next 0.3.10 gaps rather than delegating; step 4 compensates for a missing
CLI flag.

## Migration steps

For one package, in one repository:

1. Add `build_system = "build.py"` to `package.py`. Update its SHA-256 in
   `recipe.json` — the pin covers the new bytes.
2. Write `build.py` at the package root: read `recipe.json`, select the target by
   `VX_BUILD_TRIPLE`, download and verify, extract, apply `payload.mappings`
   into `$REZ_BUILD_INSTALL_PATH/payload`.
3. Point `.github/workflows/packages.yml` at the new `tooling-ref` and switch the
   build step from `tools.build_bundle` to the new wrapper.
4. Confirm the produced bundle is byte-identical to the last released one for the
   same recipe. Any difference must be explained before merge.

Everything else in `runtime-release.yml` — matrix, smoke, index, publish,
public-consumer — is untouched.

Target for a second package: **under 30 minutes**, which is steps 1, 2 and 3 plus
one CI run.

## Acceptance

- The pilot bundle is byte-identical to the current CI output for the same
  `recipe.json`, or every difference is explained and accepted.
- `tools/verify_consumer.py` and `tools/cache_bundle.py` pass unchanged against
  the pilot bundle. The zero-symlink, `payload`-naming, `package_root` and
  checksum-coverage invariants are non-negotiable.
- `build_system = "custom"` is rejected by a test, not by a code review.
- `runtime-release.yml` keeps its current gate structure; only the build step
  command changes.
