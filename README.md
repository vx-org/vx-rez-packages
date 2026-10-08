# vx-rez-packages

Prebuilt [Rez](https://github.com/AcademySoftwareFoundation/rez) package bundles for
[vx](https://github.com/loonghao/vx) runtimes.

This repository publishes every package as a **bundle**: one archive per
(package, version, platform), plus machine-readable metadata that lets a vx provider discover
versions, map a vx platform to an asset name, and report unsupported platforms clearly.

- **[SPEC.md](./SPEC.md)** is the format contract. Read it before changing anything here.
- [`index.json`](./index.json) lists every published bundle.
- [`bundles/`](./bundles) holds the per-bundle metadata and archives.

## Quick start

Validate the repository — this is exactly what CI runs:

```sh
python scripts/validate_repo.py     # check bundles + index against the schemas
python -m unittest discover -s tests -v
```

Build a bundle from a rez package tree:

```sh
python scripts/make_bundle.py \
    --source examples/python-3.11.9/src/python \
    --platform windows-x86_64
```

This writes `bundles/windows-x86_64/python/3.11.9/bundle.json`, the archives under its
`assets/` directory, and regenerates `index.json`. Builds are reproducible: rebuilding an
unchanged source yields byte-identical archives and the same checksums.

Both scripts use only the Python standard library (3.9+), so there is nothing to install.

## Format in one page

A bundle lives at `bundles/<platform>/<name>/<version>/`, where `<platform>` is a vx platform
key such as `windows-x86_64`. It contains `bundle.json` plus the archives it describes:

```json
{
  "spec_version": "1.0.0-draft",
  "name": "python",
  "version": "3.11.9",
  "platform": "windows-x86_64",
  "rez": {
    "layout": "rez-package-root",
    "package_root": "python/3.11.9",
    "install_root": "python/3.11.9",
    "package_file": "package.py"
  },
  "assets": [
    {
      "file_name": "python-3.11.9-windows-x86_64.tar.gz",
      "format": "tar.gz",
      "url": "https://github.com/vx-org/vx-rez-packages/releases/download/python-3.11.9-windows-x86_64/python-3.11.9-windows-x86_64.tar.gz",
      "size": 748,
      "sha256": "4239bd7944b20ec0…"
    }
  ],
  "commands": [
    { "name": "python", "relative_path": "python.exe" }
  ]
}
```

**The unpacked layout is the contract that matters.** `vx-rez-adapter` resolves environments
through the rez-next SDK, which recognises exactly one repository layout:

```
<root>/<name>/<version>/package.py
```

So a bundle archive wraps a rez package root rather than replacing it. Unpack to
`<cache_root>/<name>/<version>/` and hand `<cache_root>` straight to the adapter:

```rust
let request = ResolveRequest::new(["python-3.11"]).package_paths(vec![cache_root]);
let env = RezAdapter::new().resolve_env(&request)?;
```

That closes the vx#860 chain: **download → unpack to a stable cache location → resolve env →
launch the tool.**

Resolving a download needs no index round-trip beyond the fetch itself:

1. Build `platform = "<os>-<arch>"` from vx's `ctx.platform` (`macos` from `darwin`,
   `x86_64` from `x64`/`amd64`).
2. Absent from `index.json` → **report it clearly and stop**, e.g. *"Rez bundle platform
   'linux-aarch64' is not published; available platforms: windows-x86_64."* Returning `None`
   from `download_url()` for unsupported platforms, rather than raising, is the vx provider
   convention.
3. Read `bundle.json` and pick the asset matching the platform's preferred format (`zip` on
   Windows, `tar.gz` elsewhere), falling back to the first entry.
4. Verify `sha256` before extracting.

## Repository layout

| Path | Purpose |
|---|---|
| `SPEC.md` | The format contract — naming, fields, unpack rules, compatibility |
| `index.json` | Bundle index (derived data; `make_bundle.py` regenerates it) |
| `schema/` | JSON Schemas for `bundle.json` and `index.json` |
| `bundles/<platform>/<name>/<version>/` | One bundle: `bundle.json` + `assets/` |
| `examples/` | Buildable sources for the sample bundles |
| `scripts/make_bundle.py` | Generator: rez package tree → bundle |
| `scripts/validate_repo.py` | CI validator: bundles + index against the schemas |
| `scripts/release.py` | Release helper: create tags and upload release assets |
| `tests/` | Unit tests for the generator and validator |

## Releasing

Bundles are distributed as GitHub release assets, one release per bundle, tagged
`<name>-<version>-<platform>`:

```sh
python scripts/release.py --dry-run   # show what would be uploaded
python scripts/release.py             # create tags and upload assets
```

`release.py` reads `bundle.json`, checks each asset's size and SHA-256 against the archive on
disk, skips bundles whose tag already exists, and verifies the uploaded asset digest.

## Status

Spec version `1.0.0-draft`. The first release covers a single platform (`windows-x86_64`) and
one sample bundle (`python` 3.11.9), deliberately — the format is a contract once published, so
it starts small. See [SPEC.md §8](./SPEC.md#8-versioning-and-compatibility) for the
compatibility rules.

Related: [vx#860](https://github.com/loonghao/vx/issues/860) (consume bundles),
[vx#861](https://github.com/loonghao/vx/issues/861) (provider metadata).
