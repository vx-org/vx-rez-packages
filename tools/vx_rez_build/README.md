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

## Getting the `rez-next` binary

The wrapper drives the **`rez build` interface implemented by rez-next**, not the
legacy Python `rez`. Install the Rust binaries:

```bash
cargo install rez-next --locked
```

This provides both `rez` and `rez-next`, and either works — they are the same
rez-next implementation. Two things are *not* this interface:

- **The PyPI `rez_next` wheel is an empty shell.** It reports success while never
  executing `build.py`, and `get_buildsys_types()` returns `[]`. Its Python API
  (`rez_next.build_`) must not be used; run the binary instead.
- **A pip-installed legacy `rez` 3.x** also owns the `rez` name. It has no
  `--build-system` flag, so it would reject the wrapper's invocation.

Resolution order: `--rez-executable` / `$VX_REZ_EXECUTABLE` first, then `rez-next`
on `PATH`, then `rez` on `PATH`. Pinning `--rez-executable` is recommended so a
stray legacy `rez` cannot be picked up.

## Why the wrapper exists

Three measured rez-next 0.3.10 gaps make a bare `rez build` unsafe for VX:

- **No `--repository` flag.** Variants resolve through `REZ_PACKAGES_PATH`, so
  the wrapper materialises the system packages into a bootstrap repository.
- **`package.py` is not copied** by the plain build path, only by its release
  path, so the wrapper copies it byte-for-byte.
- **Only the exit code crosses back** from the subprocess, so an empty payload
  looks like a success. The wrapper asserts a non-empty payload.

The child environment is cleared before the script runs. Passing variables to
the parent `rez` process alone does not restore them. The wrapper stages a copy
of the source (excluding `.git` and `__pycache__`), preserves the pinned
`package.py`, and replaces the staged `build.py` with a bootstrap. The original
script is retained as `.vx-original-build.py`. The bootstrap reads an adjacent
temporary `.vx-build-environment.json`, restores only the explicit allowlist in
`bootstrap.py`, then runs the original script with the same phase argument.
The sidecar carries `PATH`, Windows temporary/runtime paths, named HTTP proxy
variables, `REZ_PACKAGES_PATH`, `VX_BUILD_TRIPLE` and `VX_BUILD_RECIPE`. It does
not copy the entire parent environment and is not part of the payload bundle.
The parent also sets
`REZ_BUILD_TARGET_PLATFORM` / `_ARCH` / `_OS`, which rez-next reads but never
sets (unset, they silently default to the host).

## Only `build_system = "build.py"` is accepted

The wrapper requires exactly one direct literal assignment and rejects
duplicates, indirect bindings, all other names, and any `build_command`
override. In rez-next 0.3.10, `default` and `copy-only` copy files, while
`build_command` executes a separate command during installation. These modes
do not satisfy this wrapper's named Python-script contract. `custom` is also
refused; it must not be described as universally copy-only.

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

The real `witr` pilot remains an adoption gate. A subprocess environment smoke
does not prove bundle equivalence or SDK `installation-plan` compatibility.
