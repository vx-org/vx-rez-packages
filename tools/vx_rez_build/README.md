# vx-rez-build

Status: **proposed**. The mechanism is verified against rez-next 0.3.10, but no
VX package has been migrated yet, so treat the command surface as unstable.

A thin wrapper that lets a VX Rez package build itself through `rez build`
instead of being assembled by CI. It replaces only the **assembly** half of
[`tools/build_bundle.py`](../build_bundle.py); the published bundle contract is
untouched.

## What it does

```bash
python -m tools.vx_rez_build.cli \
  --definition recipe.json \
  --triple x86_64-pc-windows-msvc \
  --output-dir out/
```

It validates the recipe, selects the target, resolves the variant through the
SDK's `installation-plan`, stages the sibling `platform/` and `arch/` system
packages, copies the pinned `package.py`, runs `rez build`, asserts the payload
is non-empty, and emits a repository ready for the pack stage.

Deterministic `tar.zst`, `sha256sums.txt`, `manifest.json` and consumer
verification are **not** done here — they remain in
[`tools/pack_stage.py`](../pack_stage.py), which this wrapper shares with
`build_bundle.py` so both paths produce byte-identical archives.

## Getting the `rez` binary

The wrapper shells out to the `rez` Rust binary. The PyPI `rez_next` wheel is an
empty shell: it reports success while never executing `build.py`, and
`get_buildsys_types()` returns `[]`. Install the binaries instead:

```bash
cargo install rez-next --locked
```

This provides both `rez` and `rez-next`. Point the wrapper at a specific binary
with `--rez-executable` or the `VX_REZ_EXECUTABLE` environment variable.

## Why the wrapper exists

Three measured rez-next 0.3.10 gaps make a bare `rez build` unsafe for VX:

- **No `--repository` flag.** Variants resolve through `REZ_PACKAGES_PATH`, so
  the wrapper materialises the system packages into a bootstrap repository.
- **`package.py` is not copied** by the plain build path, only by its release
  path, so the wrapper copies it byte-for-byte.
- **Only the exit code crosses back** from the subprocess, so an empty payload
  looks like a success. The wrapper asserts a non-empty payload.

The child environment is also cleared before the script's own is applied — on
Windows that leaves **no `PATH`**, so `build.py` cannot shell out. The wrapper
restores `PATH`, `TEMP`, `TMP`, `SystemRoot` and friends, and sets
`REZ_BUILD_TARGET_PLATFORM` / `_ARCH` / `_OS`, which rez-next reads but never
sets (unset, they silently default to the host).

## `build_system = "custom"` is refused

rez-next resolves any unrecognised build system to `Custom(<value>)`, and
`custom` degenerates to a **copy-only build in which the script never runs**.
That is a silent no-op that looks like a successful release, so the wrapper
rejects it before invoking `rez`. Use `build_system = "build.py"`.

## Environment handed to `build.py`

| Variable | Meaning |
| -------- | ------- |
| `REZ_BUILD_INSTALL_PATH` | variant root; write `payload/` under it |
| `REZ_BUILD_TARGET_PLATFORM` / `_ARCH` / `_OS` | target triple, derived from the recipe |
| `REZ_PACKAGES_PATH` | bootstrap repository with the sibling system packages |
| `VX_BUILD_TRIPLE` | the recipe's `targets[].triple` |
| `VX_BUILD_RECIPE` | absolute path to `recipe.json` |

`build.py` runs from a temporary copy, not the package root, so `recipe.json`
must be resolved through `VX_BUILD_RECIPE` rather than relative to `__file__`.
See [`docs/build-py-contract.md`](../../docs/build-py-contract.md) for the full
contract.
