# Spike: can VX packages be built with `rez build`?

Answer: **yes for package construction, no for the published artifact.** `rez build`
reproduces the VX bundle repository layout natively and ran a real `build.py`
end to end on 0.3.10. It cannot replace the *release* half of the pipeline
(deterministic `tar.zst`, `sha256sums.txt`, `manifest.json`, consumer
verification), because none of that exists upstream and all of it is VX's
published schema-v1 contract.

That split is the recommended shape of the work. It means the migration is much
smaller than "rewrite the builder": one pipeline stage changes, and the published
contract is never at risk.

Verified against `vx-org/rez-next` **0.3.10**, October 2026.

## The headline result

A minimal package with `build_system = "build.py"` and one variant, built with:

```console
$ export PYTHON=<venv>/Scripts/python.exe          # so rez_next.build_plugins imports
$ export REZ_PACKAGES_PATH=$PWD/repo               # where platform/ and arch/ live
$ rez-next build pkg --install --prefix repo --build-system build.py --variants 0
All 1 build(s) were successful.
```

produced:

```text
repo/spike/0.0.1/platform-windows/arch-x86_64/payload/bin/spike.txt
```

That is character-for-character the layout VX already publishes:

```text
witr/0.3.4/platform-<platform>/arch-<arch>/payload/bin/witr[.exe]
```

The build ran the script twice, as `build` then `install`, and the payload landed
under the variant root. **Layout is not a gap.** The gaps are all in the
surroundings — environment, determinism, and the release artifacts.

## Do not build this on the Python wheel

The PyPI wheel imports, but its build surface is inert:

```console
$ uv pip install rez-next==0.3.10
$ python -I -c "import rez_next; print(rez_next.__version__)"
0.3.10

$ python -I -m rez_next build --help
rez_next version 0.3.10          # banner only; no CLI dispatch

$ python -I -c "from rez_next._native.cli import cli_main; cli_main()"
NotImplementedError: Python CLI dispatch is not available; run the `rez` or `rez-next` executable instead

$ python -I -c "from rez_next.build_system import get_buildsys_types, get_valid_build_systems
                print(get_buildsys_types()); print(get_valid_build_systems('pkg'))"
[]
[]
create_build_system('custom') -> RuntimeError: Package definition file not found at: custom
```

An end-to-end attempt is worse than an empty registry, because it fails
**silently**:

```console
$ python -I -c "from rez_next.build_ import build_package
                build_package('pkg', install=True, install_path='repo')"
Build succeeded: 1 builds completed

$ find repo -type f
# (nothing)
```

`repo/spike/0.0.1/` was created and left empty: `build.py` never ran and
`package.py` was never copied. `rez_next.build_.build_package()` in 0.3.10 is a
path-shaped stub, not a working port.

**Consequence:** a `vx build` wrapper cannot be a thin Python wrapper over
`rez_next.build_*`. It must invoke the **`rez` / `rez-next` Rust binary**
(`cargo install rez-next --locked`, which yields both `rez` and `rez-next`).

## Measured behaviour of `rez build` 0.3.10

Dumped from inside a real `build.py` run. These are observed values, not
documentation:

```json
{
  "argv":                       ["<temp>/rez-core-build-cache/spike-0.0.1-<pid>/build.py", "install"],
  "cwd":                        "<temp>/rez-core-build-cache/spike-0.0.1-<pid>",
  "install_path":               "<prefix>/spike/0.0.1/platform-windows/arch-x86_64",
  "source_path":                "<temp>/rez-core-build-cache/spike-0.0.1-<pid>",
  "build_path":                 "<cwd>/.rez_build/spike",
  "package_name":               "spike",
  "package_version":            "0.0.1",
  "variant_index":              0,
  "target_platform":            "windows-amd64",
  "target_arch":                "amd64",
  "REZ_BUILD_TARGET_PLATFORM":  null,
  "REZ_BUILD_TARGET_ARCH":      null,
  "REZ_BUILD_TARGET_OS":        null,
  "PATH":                       null,
  "TEMP":                       "C:\\Users\\...\\Temp",
  "SystemRoot":                 "C:\\WINDOWS"
}
```

Five things follow, and each one is a contract clause rather than a preference:

1. **`build.py` is copied to a temp build cache and run there.** `cwd`,
   `__file__` and `REZ_BUILD_SOURCE_PATH` all point at
   `%TEMP%/rez-core-build-cache/...`, *not* at the package root. A `build.py`
   cannot find `recipe.json` by relative path — the wrapper must hand it an
   absolute path.
2. **`PATH` is not set.** The child environment is cleared and only
   `TEMP`/`TMP`/`SystemRoot`/`WINDIR` are restored on Windows. A `build.py` that
   shells out to anything — `7z`, `git`, `curl`, `tar` — fails unless the wrapper
   supplies `PATH`.
3. **`REZ_BUILD_TARGET_PLATFORM` / `_ARCH` / `_OS` are never set.** `BuildContext`
   reads them but falls back to the *host*, so `target_arch` came back as
   `amd64` and `target_platform` as `windows-amd64`. A cross-target build would
   silently believe it is building for the host.
4. **`amd64`, not `x86_64`.** The host arch Rez reports does not match the
   `arch-x86_64` package family VX uses. Any mapping through `target_arch` needs
   an explicit translation table.
5. **`package.py` is not copied.** The variant root contained only `payload/`.
   The plain build path never writes the definition; only the release path does.

Two further observations:

- **Variant resolution needs `REZ_PACKAGES_PATH`.** `rez build` has no
  `--repository` flag (unlike `rez-next-runtime installation-plan`, which does).
  Pointing `REZ_PACKAGES_PATH` at a repository that contains the sibling
  `platform/` and `arch/` system packages is what made the variant resolve;
  without it the solver fails with
  `Strict mode: failed to satisfy requirements: platform-windows, arch-x86_64`.
- `custom` marshals **exit code only**. Nothing checks that the script wrote
  anything, so a missing payload is a silent success.

## What exists upstream

`rez-next` ships two binaries (`rez`, `rez-next`) with a `build` subcommand
carrying the flags this migration needs:

```text
-i/--install            install into a package repository
-p/--prefix PATH        the repository to install into
-b/--build-system NAME  override detection
--variants INDEX        build selected variants only
--ba/--build-args ARGS  pass-through to the build system
-f/--force  -c/--clean  -s/--scripts  --view-pre  --process  --skip-tests
```

`crates/rez-next-build` provides eight build systems: `cmake`, `make`, `python`,
`nodejs`, `cargo`, `binary_archive`, `pypi`, `custom`. The crate is not a stub —
no `todo!`/`unimplemented!`/`FIXME` in `src/`, and roughly 170 test attributes.

### `custom` is the build.py mechanism

`CustomBuildSystem` holds a `script_name`. Three values are magic tokens
(`default`, `copy-only`, `build_command`); **anything else is treated as a file
name relative to the package root** and executed with argv
`build` / `install` / `test`. The script runs under
`runpy.run_path(script, run_name="__main__")` with `rez_next.build_plugins`
injected (imported if present, otherwise synthesised from an embedded copy).

One trap worth writing into the contract: **`build_system = "custom"` resolves to
`Custom("default")`, i.e. copy-only — the script is silently never executed.**
Use `build_system = "build.py"`.

`rez_next.build_plugins` ships helpers VX `build.py` files should use rather than
reimplement: `BuildContext.from_env()`, `BuildPlugin` (with `build()` /
`install()` / `run()`), `ExtractionBuilder` (download → verify → extract →
prefix → copy), `verify_sha256()`, `extract_archive()`, `copy_tree_contents()`.

### `binary_archive` is close but not sufficient

It is entirely environment driven — `REZ_BINARY_ARCHIVE_ARTIFACT` or `_URL`,
`_SHA256`, `_PAYLOAD_PREFIX` — and does download → SHA-256 → extract → strip
prefix → copy into the install dir. That is the same shape as today's pipeline.
It accepts only `.zip`, `.whl`, `.tar.gz`, `.tgz`.

## Gap register

| # | Gap | Evidence | Impact | Fix where |
| - | --- | -------- | ------ | --------- |
| G1 | Python build API inert; no CLI dispatch | `build_package()` returns success leaving an empty dir | wrapper must shell out to the Rust binary | upstream issue; local ships/pins a binary |
| G2 | `binary_archive` accepts only zip/tar.gz/tgz | `systems/binary_archive.rs`, `extract_archive()` | `python` 3.7.9 recipe is `tar.zst` | upstream: add zstd; local: extract inside `build.py` |
| G3 | No determinism primitives: no `SOURCE_DATE_EPOCH`, no mtime/mode/uid normalisation, no sorted entries, no `tar.zst` output, no `sha256sums.txt` / `manifest.json` / `provenance.json` | no hits for any of these in the build crate | `rez build` cannot produce the published `.rez.tar.zst` | local — VX's own contract, keep the pack stage |
| G4 | `REZ_BUILD_TARGET_*` never set; defaults to host | observed `null`, `target_arch: amd64` | cross-target builds silently target the host | local: wrapper sets them; upstream: set them |
| G5 | Plain build path never copies `package.py` | variant root contained only `payload/` | package would ship without its definition | local: wrapper copies it |
| G6 | Child env cleared; **`PATH` not restored** | observed `"PATH": null` | `build.py` cannot shell out | local: wrapper defines an explicit env contract |
| G7 | `custom` marshals exit code only | observed | missing payload is a silent success | local: pack stage asserts a non-empty payload |
| G8 | `create_build_system("custom")` degrades to copy-only | `lib.rs` | a plausible-looking `package.py` silently no-ops | local: contract forbids the literal, test asserts it |
| G9 | `build.py` runs from a temp copy; `source_path` is that temp dir | observed `cwd`/`__file__` | `build.py` cannot find `recipe.json` relatively | local: wrapper passes an absolute recipe path |
| G10 | Host arch reported as `amd64`, family is `arch-x86_64` | observed | wrong variant subpath if mapped naively | local: explicit arch translation table |

## Recommendation

Keep three layers, and add only the middle one.

1. **`recipe.json` — unchanged.** It stays the single declarative source: targets,
   upstream URL and SHA-256, payload mappings, metadata and notice files, smoke
   test. Nothing is described twice.
2. **`build.py` — new, one per package.** Builds **one** target's payload into the
   variant root. Selected by `build_system = "build.py"` in `package.py`.
3. **`vx build` — new, thin wrapper.** Reads `recipe.json`, resolves the target for
   the current host, sets the environment contract (G4, G6, G9), sets
   `REZ_PACKAGES_PATH`, runs `rez build --install --prefix <repository>`, copies
   `package.py` (G5), asserts a non-empty payload (G7), then hands the repository
   to the pack stage.

The pack stage is not new work: `tools/build_bundle.py` already ends with a
deterministic, sorted, normalised `tar.zst` writer plus checksum emission
(`_write_reproducible_tar_zstd`, `_write_repository_checksums`). Splitting it out
is a small, well-tested extraction.

`runtime-release.yml` then degrades exactly as intended — one step changes from
"run `build_bundle.py`" to "run `vx build`". Matrix generation, native smoke,
index generation, publish and public-consumer verification are untouched.

## Pilot choice

Only **two** VX repositories are Rez packages today: `vx-org/witr` and
`vx-org/python`. (`vx-org/vx` has no `recipe.json` and no `package.py` — it is
the CLI, not a package.)

- **`witr` first.** Six targets, payloads are `zip` on Windows and bare `binary`
  elsewhere, so it avoids G2 entirely. Smallest possible end-to-end proof.
- **`python` second.** Its `tar.zst` payloads hit G2 head-on; attempt it only
  once the zstd question is settled upstream or absorbed into `build.py`.

## Decisions still open

1. **Naming.** `vx build` collides with the `vx` CLI's own namespace. Recommended:
   repository `vx-org/vx-rez-build`, command `vx-rez-build`, delegating to
   `rez build`. Revisit a `vx` extension subcommand later — `rez-next` ships a
   `vx-extension.toml`, so that route exists.
2. **`red build`.** This spike read the request as **rez / rez-next**. If `RED` is
   a separate internal platform, the encapsulation target and the naming both
   change and this document is void.
3. **Upstream vs local for G2 and G4.** Both are small upstream asks. The
   preferred order is upstream issue first, local compensation only if blocked.
4. **How CI obtains the `rez` binary.** `cargo install rez-next --locked` works
   but is slow. Options: a pinned prebuilt binary asset, or a cached cargo
   install in the reusable workflow.
