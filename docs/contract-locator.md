# Where the bundle contract lives

This document is a map, not a specification. It records where each part of the
Rez bundle contract is defined so a consumer can find it without reading the
whole repository. Every claim below points at the file that enforces it; when
this document and code disagree, the code and its schemas win.

The authoritative contract is the four JSON schemas in `schema/`. There is
exactly one contract in this repository — no second specification exists, and
none should be added.

## Artifact chain

```text
recipe (bundle-definition.schema.json)
  └─ build_bundle.py ──► .rez.tar.zst asset  (directly extractable Rez repository)
                     └──► manifest.json     (bundle-manifest.schema.json)
  └─ generate_index.py ─► index.json        (release-index.schema.json)
                                              └─► collected into catalog.json
                                                    (catalog.schema.json, docs/catalog.md)
```

Each `.rez.tar.zst` asset extracts straight into a Rez repository, so a consumer
needs no unpacking step of its own:

```text
witr/0.3.4/package.py
witr/0.3.4/payload/bin/witr[.exe]
witr/0.3.4/LICENSE
witr/0.3.4/THIRD_PARTY_NOTICES.txt
witr/0.3.4/provenance.json
witr/0.3.4/manifest.json
witr/0.3.4/sha256sums.txt
platform/<platform>/package.py
arch/<arch>/package.py
```

## The five contract points

### 1. Version discovery — `schema_version: 1`

Every published index declares `schema_version`, pinned to the literal `1`.
`schema/release-index.schema.json` and `schema/catalog.schema.json` both declare
it as `"const": 1`, and `tools/generate_index.py` emits it as the first key of
the index. A consumer reads this field to decide whether it can interpret the
rest of the document at all.

### 2. Platform and architecture mapping — `triple`

Each bundle entry in the index carries `platform`, `arch`, and `triple`
(`tools/generate_index.py`, in the per-target bundle record). `platform` is
constrained to `windows`, `linux`, or `osx`; `arch` to `x86_64` or `arm_64`.
`triple` is the string a consumer matches against its own target, and it is also
what names the asset (`tools/generate_index.py` derives
`<tool>-<version>-<triple>.rez.tar.zst`).

### 3. Unsupported platforms — `unsupported_targets`

A target that cannot be built is reported explicitly rather than omitted.
`tools/generate_index.py` copies `unsupported_targets` from the recipe into the
index, and `schema/release-index.schema.json` requires the key — so an index
without it is invalid, not merely uninformative. Each entry carries `triple`,
`status` (constant `unsupported`), and a human-readable `reason`.

`validate_definition` in `tools/build_bundle.py` additionally checks that no
triple appears in both `targets` and `unsupported_targets`, so a platform can
never be simultaneously supported and unsupported.

### 4. The package root — `<tool>/<version>`

This is the point the whole format exists to satisfy. `tools/generate_index.py`
sets:

```python
"package_root": f"{definition['tool']}/{definition['version']}"
```

Combined with the asset tree above, an extracted bundle therefore contains
`<tool>/<version>/package.py`. That is exactly the layout a Rez consumer expects
under a package repository root — `<root>/<name>/<version>/package.py` — which is
what lets the extracted directory be handed to a resolver as a package path.

`tools/cache_bundle.py` relies on this: `_verify_repository` resolves
`package_root` relative to the extracted repository and verifies the manifest and
per-file checksums underneath it. If `package_root` ever stopped being
`<tool>/<version>`, that verification and every downstream consumer would break.

### 5. Verification — manifest, checksums, catalog

Verification is layered, and each layer is enforced by a schema:

| Layer | Defined by | Enforced at |
|---|---|---|
| Recipe shape | `schema/bundle-definition.schema.json` | `tools/build_bundle.py` |
| Bundle contents | `schema/bundle-manifest.schema.json` | `tools/build_bundle.py` |
| Release index | `schema/release-index.schema.json` | `tools/generate_index.py` |
| Cross-repo catalog | `schema/catalog.schema.json` | `tools/catalog.py` |

A bundle manifest pins the package, payload, upstream, and all-regular-files
checksums; the repository additionally carries `sha256sums.txt`.
`tools/cache_bundle.py` re-verifies every checksum after extraction and fails
closed on any mismatch. The catalog layer adds a digest-pinned directory of
release indexes; see `docs/catalog.md`.

Additive changes keep `schema_version: 1`. Removing or reinterpreting a field,
or changing the meaning of `package_root`, is a breaking change and requires a
new schema version.

## Scope boundaries

This repository owns the build, index, and catalog contracts — artifact
discovery and verified local repositories. It deliberately does not own:

- package reading, dependency solving, variants, or environment commands —
  those belong to the consuming SDK;
- proof of public publication, native application behavior, or acceptance by an
  installed consumer — record those delivery gates separately.

Runtime recipes live in their own repositories, starting with
[vx-org/witr](https://github.com/vx-org/witr). This repository does not publish
placeholder runtime packages or maintain a second runtime registry.
