# Rez Bundle Format and Provider Metadata

**Spec version:** 1.0.0-draft
**Status:** draft — first version covers a single platform and a single version per bundle.
**Reference issues:** vx#860 (consume bundles), vx#861 (provider metadata for bundle assets)

This repository publishes prebuilt [Rez](https://github.com/AcademySoftwareFoundation/rez)
packages as **bundles**: one archive per (package, version, platform), plus machine-readable
**provider metadata** that lets a vx provider discover versions, map a vx platform to an
asset name, and report unsupported platforms clearly.

---

## 1. Why this format exists

`vx-rez-adapter` resolves package environments through the rez-next SDK. Its resolve step
recognises exactly one repository layout — the rez layout:

```
<root>/<name>/<version>/package.py
```

Roots come from `REZ_PACKAGES_PATH` or `ResolveRequest::package_paths`. Therefore the contract
that matters is not only what is *inside* the archive, but what the archive **unpacks into**:
after extraction the bundle must land as a rez package root, or the chain
*vx unpacks to a stable cache location → adapter resolves env → tool launches* is broken.

Two consequences drive the rest of this document:

1. **The unpacked layout is a first-class part of the format.** A bundle archive wraps a
   rez package root, it does not replace it.
2. **The bundle carries its own metadata file**, so a consumer can validate and place it
   without consulting a network index.

## 2. Repository layout

```
vx-rez-packages/
├── SPEC.md                  # this document — the format contract
├── README.md                # orientation and quick start
├── index.json               # bundle index: every published bundle (see §5)
├── schema/                  # JSON Schemas
│   ├── bundle.schema.json     # validates  bundle.json
│   └── index.schema.json      # validates  index.json
├── bundles/<platform>/<name>/<version>/
│   ├── bundle.json          # per-bundle metadata + asset list (see §4)
│   └── assets/              # the archive(s) for this platform
│       └── <asset-file-name>
├── examples/                # buildable sources for the sample bundles
│   └── python-3.11.9/src/python/
├── scripts/
│   ├── validate_repo.py     # CI validator: bundles + index against the schemas
│   ├── make_bundle.py       # generator: rez package tree -> bundle
│   └── release.py           # release helper: push tags and GH release assets
└── tests/
    └── test_format.py       # unit tests for the validator and generator
```

Platform directory names and asset file names are **not** free-form; they are derived by the
naming rules in §3 so a provider can construct a URL without reading the index first.

## 3. Naming rules

### 3.1 Platform directory

`bundles/<platform>/`, where `<platform>` is the vx platform key:

```
<os>-<arch>
```

with `<os>` ∈ `windows` | `linux` | `macos` and `<arch>` ∈ `x86_64` | `aarch64` | `x86`.

These are the keys vx already uses for `runtimes.layout.binary` platform maps
(`crates/vx-manifest/src/provider/layout.rs`), so a provider maps `ctx.platform` to a bundle
path with no new vocabulary. This first version ships `windows-x86_64` only.

### 3.2 Asset file name

```
<name>-<version>-<platform>.tar.gz
```

Windows bundles are also published as `.zip`. Both archives hold **byte-identical** members;
the archive format is a transport detail, not part of the identity of the bundle. The
`bundle.json` asset list carries the `sha256` of each archive separately.

### 3.3 Download URL

Bundles are distributed as GitHub release assets on this repository. For release tag
`python-3.11.9-windows-x86_64`:

```
https://github.com/vx-org/vx-rez-packages/releases/download/<tag>/<asset-file-name>
```

## 4. `bundle.json`

One file per bundle, at `bundles/<platform>/<name>/<version>/bundle.json`. It is the
authoritative description of a single (package, version, platform) trio.

### 4.1 Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `spec_version` | string | yes | Spec this bundle conforms to. Must be `"1.0.0-draft"`. Lets a consumer reject a bundle it cannot read instead of mis-reading it. |
| `name` | string | yes | Rez package name. `^[a-z][a-z0-9_]*$`. |
| `version` | string | yes | Rez package version, a dot-separated numeric string (`1`, `1.2`, `1.2.3`). |
| `platform` | string | yes | vx platform key (§3.1). Must equal the `<platform>` directory this file lives in. |
| `rez` | object | yes | How the bundle materialises as a rez package. See §4.2. |
| `assets` | array | yes | One or more downloadable archives. See §4.3. |
| `requires` | array | no | Rez request strings this package needs, e.g. `["python-3.11"]`. |
| `build` | object | no | Provenance: what produced the bundle. See §4.4. |
| `commands` | array | no | Rez command definitions this package contributes. See §4.5. |

### 4.2 `rez` object

Describes the unpacked result — the part `vx-rez-adapter` actually consumes.

| Field | Type | Required | Description |
|---|---|---|---|
| `layout` | string | yes | Always `"rez-package-root"`. The only value this spec version defines. |
| `package_root` | string | yes | Path **inside the archive** of the directory that becomes the rez package root — the directory holding `package.py`. |
| `install_root` | string | yes | Stable cache location the bundle unpacks to, relative to the vx package cache root. See §6. |
| `package_file` | string | yes | Name of the package definition file inside `package_root`. Always `"package.py"` in this spec version. |
| `commands` | array | no | Mirrors the top-level `commands` field; see §4.5. |

### 4.3 `assets[]` entries

| Field | Type | Required | Description |
|---|---|---|---|
| `file_name` | string | yes | Archive file name, matching §3.2. |
| `format` | string | yes | `tar.gz` or `zip`. |
| `url` | string | yes | Absolute download URL. |
| `size` | integer | yes | Size in bytes; lets a consumer show progress and detect truncation. |
| `sha256` | string | yes | Lowercase hex SHA-256 of the archive. Always verified before extraction. |

### 4.4 `build` object (optional)

| Field | Type | Required | Description |
|---|---|---|---|
| `requirement` | string | no | Source requirement this bundle was produced from. |
| `generator` | string | no | Generator identifier, e.g. `make_bundle.py/1.0`. |
| `generated_at` | string | no | RFC 3339 UTC timestamp. |
| `source` | object | no | Upstream provenance. Free-form: typically `{"type": "...", "owner": "...", "repo": "...", "version": "..."}`. |

### 4.5 `commands[]` entries

Rez exposes package-provided commands (`rez-env --paths`, `which`, `rez plugins`). A bundle can
declare the commands it contributes so a provider can wire up shims without parsing `package.py`.

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Command name. |
| `relative_path` | string | no | Executable path relative to `package_root`. Omitted when the command is a
shell/batch wrapper resolved by rez rather than a file in the payload. |

### 4.6 Example

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
      "size": 2048,
      "sha256": "…"
    }
  ],
  "requires": [],
  "commands": [
    { "name": "python", "relative_path": "python.exe" },
    { "name": "pythonw", "relative_path": "pythonw.exe" }
  ],
  "build": {
    "requirement": "python-3.11.9",
    "generator": "make_bundle.py/1.0",
    "generated_at": "2026-10-08T00:00:00Z",
    "source": { "type": "python-build-standalone", "version": "3.11.9" }
  }
}
```

## 5. `index.json`

The repository-level bundle index, at the repo root. It is the answer to vx#861 acceptance
criterion 1: *providers can discover versions from release/index metadata.*

```json
{
  "spec_version": "1.0.0-draft",
  "updated_at": "2026-10-08T00:00:00Z",
  "platforms": ["windows-x86_64"],
  "packages": [
    {
      "name": "python",
      "versions": ["3.11.9"],
      "platforms": ["windows-x86_64"],
      "bundle": "bundles/windows-x86_64/python/3.11.9/bundle.json"
    }
  ]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `spec_version` | string | yes | Spec version, as in §4.1. |
| `updated_at` | string | yes | RFC 3339 UTC timestamp of the last regeneration. |
| `platforms` | array | yes | Union of all platforms published by this repository. A provider uses this to report an unsupported platform clearly (vx#861 criterion 3) rather than failing with a missing-file error. |
| `packages[]` | array | yes | One entry per package name. |
| `packages[].name` | string | yes | Rez package name. |
| `packages[].versions` | array | yes | All published versions of that package, sorted ascending. |
| `packages[].platforms` | array | yes | Platforms this package is published for. |
| `packages[].bundle` | string | yes | Repo-relative path to the newest version's `bundle.json`. |

The index is **derived data**: `scripts/validate_repo.py` recomputes it from the bundle tree on
every CI run and fails if the committed file differs. Nobody edits it by hand.

### Mapping vx platform/arch to asset names (vx#861 criterion 2)

Given a vx `ctx.platform` (`os`, `arch`) and a requested version, a provider resolves an asset
with no network round-trip beyond the download itself:

1. `platform = "{os}-{arch}"`, mapping vx's `macos` from `darwin` and `x86_64` from `x64`/`amd64`.
2. Look up `platform` in `index.json`.`platforms`.
   **Absent → report clearly and stop.** *"Rez bundle platform 'linux-aarch64' is not published;
   available platforms: windows-x86_64."* This is the vx#861 criterion-3 path.
3. Look up the package in `index.json`.`packages` and check `platform` is in its `platforms`.
   Absent package → "no rez bundle published for 'maya'"; absent platform → as above.
4. Read `bundle.json` at `packages[].bundle` (or at the well-known path for an explicit version).
5. Pick the asset whose `format` the platform prefers — `zip` on Windows, `tar.gz` elsewhere —
   falling back to the first entry.

Returning `None` from `download_url()` for an unsupported platform, rather than raising, is the
convention vx providers already follow (`.github/instructions/starlark-providers.instructions.md`).

## 6. Unpacked layout and the stable cache location

vx#860 criterion 2 requires bundles to be extracted into a **stable cache location**. A bundle
declares that location itself, in `rez.install_root`, as a path relative to the vx rez package
cache root:

```
<package_cache_root>/<rez.install_root>/
```

For the sample bundle that is `<package_cache_root>/python/3.11.9/`. The path is deliberately
identical to the rez package's own `<name>/<version>` pair, so the cache root can be handed
straight to `vx-rez-adapter` as a package path:

```rust
let request = ResolveRequest::new(["python-3.11"]).package_paths(vec![cache_root]);
let env = RezAdapter::new().resolve_env(&request)?;
```

This is what closes the vx#860 chain: **unpack to `<cache_root>/<name>/<version>/` → pass
`<cache_root>` to the adapter → resolve → launch.** Consumers must not flatten the archive or
rename its top-level directory; `rez.package_root` names the directory inside the archive that
must survive extraction.

## 7. Verification

A bundle is valid only when all of the following hold. `scripts/validate_repo.py` enforces
1–5 in CI:

1. `bundle.json` parses as JSON and validates against `schema/bundle.schema.json`.
2. `bundle.name` / `bundle.version` / `bundle.platform` equal the directory path
   `bundles/<platform>/<name>/<version>/`.
3. `version` is a dot-separated numeric string.
4. Every asset has `file_name`, `format`, `url`, a positive integer `size`, and a 64-char
   lowercase hex `sha256`.
5. `index.json` validates against `schema/index.schema.json` and matches the bundle tree
   recomputed by the validator.
6. *(Release-time, not CI)* the real asset exists at `url`, is `size` bytes, and hashes to
   `sha256`. CI cannot reach release assets of an unmerged branch, so the URL is checked for
   shape only; `scripts/release.py` verifies the digest after upload.

## 8. Versioning and compatibility

- `spec_version` is bumped on any incompatible change to `bundle.json` or `index.json`.
- **Additive** changes (a new optional field, a new platform key) keep the existing
  `spec_version`; consumers must ignore unknown fields.
- Removing or reinterpreting a required field, or changing a naming rule, is a major bump.
- The unpacked layout (`rez.layout = "rez-package-root"`) is the part most likely to become
  a compatibility constraint: it is what `vx-rez-adapter` consumes, so it changes only with a
  spec version bump.
