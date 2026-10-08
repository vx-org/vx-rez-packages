# vx-rez-packages

One shared builder and schema-v1 release contract for real VX runtime Rez packages.
Runtime recipes live in their own repositories, starting with
[vx-org/witr](https://github.com/vx-org/witr). This repository does not publish
placeholder runtime packages or maintain a second runtime registry.

Each `.rez.tar.zst` asset is a directly extractable Rez repository:

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

The index preserves `schema_version: 1` and the consumer fields `tool`, `version`,
`platform`, `arch`, `triple`, `asset_name`, `download_url`, `sha256`, `package_root`
and `bundle_schema_version`. The manifest preserves the corresponding package,
payload, upstream and all-regular-files checksum fields. Repository ownership is
passed to the index generator; a package release belongs to its runtime repository.

Recipes use the JSON schema in `schema/bundle-definition.schema.json`. They declare
the package description, Rez tools, PATH entries, native smoke command, pinned
upstream revision/source archive, hashed legal metadata and target assets. Each
target chooses `binary`, `zip` or `tar` and maps source paths into `payload/`.
A directory mapping preserves an application's resources and libraries. Safe
internal links are materialized as regular content so every payload byte is
hashed and portable caches need no link support. Directory aliases can duplicate
framework resources. Blender and FreeCAD can use the same builder with their own
recipes; their payloads and native behavior still require separate validation.
There are no runtime-specific branches in the builder.

The builder checks the upstream SHA-256 before extraction, validates the full
archive member graph, rejects traversal, escaping links, device files and portable
path collisions, and checks copied links again. It writes deterministic sorted
TAR/Zstandard output with normalized timestamps, owners and modes. Every regular
repository file except the checksum list itself is hashed. Upstream license and
third-party notice files are digest-pinned recipe inputs and included in every
target. `tools.collect_notices` collects actual legal texts from a verified source
archive without inventing attribution.

From this repository, with a runtime recipe checkout at `../witr`:

```bash
vx uv sync --locked
vx uv run --locked python -m unittest discover -s tests -v
vx uv run --locked ruff format --check .
vx uv run --locked ruff check .
vx uv run --locked python -m tools.build_bundle --definition ../witr/recipe.json --triple x86_64-pc-windows-msvc --output-dir dist
vx uv run --locked python -m tools.generate_index --definition ../witr/recipe.json --asset-dir dist --repository vx-org/witr --release-tag witr-0.3.4 --output dist/index.json
```

`--source-archive` accepts an already downloaded upstream asset and still verifies
its digest. `--no-smoke-test` permits packaging foreign targets for inspection;
it does not establish native execution. Index generation requires every declared
target asset and companion checksum. A native smoke is required by the reusable
workflow for every target before release publication.

Runtime repositories call `.github/workflows/runtime-release.yml` at an immutable
builder commit and pass the same commit as `tooling-ref`. Pull requests build all
targets without publishing. Tag releases publish only after all native jobs and
index validation pass and the tag matches `<tool>-<version>`. Publication creates
a draft, downloads every uploaded asset and compares its names and SHA-256 with
the validated local release before making the draft public. The workflow then
reads back public release metadata and checksum companions; installed VX
acceptance remains a separate consumer gate.
