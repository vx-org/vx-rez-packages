# vx-rez-packages

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/vx-org/.github/main/profile/assets/vx-symbol-dark.svg">
  <img src="https://raw.githubusercontent.com/vx-org/.github/main/profile/assets/vx-symbol-light.svg" width="48" alt="VX symbol">
</picture>

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

Recipes use the JSON schema in `schema/bundle-definition.schema.json`. Every recipe
must pin its checked-in Rez definition, for example
`"package": {"definition": {"source": "package.py", "sha256": "<raw file SHA-256>"}, ...}`.
The source path is relative to the recipe directory (or `--metadata-dir`), must
remain inside it, and must name a regular file. The builder verifies those bytes,
checks direct literal `name` and `version` declarations against the recipe using
Python AST, and copies exactly the same bytes into the bundle. It rejects duplicate
or additional module identity bindings and never executes the package source.
This is declaration validation, not a sandbox for code executed later by a Rez
consumer. The actual file owns dependencies, variants, tools and environment
commands. No package definition is generated as a fallback. Existing recipe
`description`, `tools` and `path_entries` fields remain descriptive expectations;
they do not rewrite the copied definition.

Recipes also declare a native smoke command, pinned
upstream revision/source archive, hashed legal metadata and target assets. Each
target chooses `binary`, `zip`, `tar`, `tar.zst` or `7z` and maps source paths into `payload/`.
`tar.zst` is decoded with Zstandard into a private temporary TAR, then uses the
same complete member preflight and safe extraction as other TAR payloads. This
works independently of the host Python version's built-in compression support.
A directory mapping preserves an application's resources and libraries. Safe
internal links are materialized as regular content so every payload byte is
hashed and portable caches need no link support. Directory aliases can duplicate
framework resources. Blender and FreeCAD can use the same builder with their own
recipes; their payloads and native behavior still require separate validation.
There are no runtime-specific branches in the builder.

An optional target-level `smoke_test` replaces the package-level smoke command,
expected output and timeout together. Both use the same schema and enforce native
platform/architecture plus an executable inside the isolated package copy. This
lets a portable recipe declare the actual Windows and Unix executable layouts.

7z payloads use py7zr by default. A recipe may explicitly select
`"payload": {"format": "7z", "decoder": "native-7zip", "mappings": [...]}`
for methods such as BCJ2 that py7zr cannot decode. This invokes `vx 7zip` with
separate arguments and requires official 7-Zip 26.04 or newer; the minimum follows
the vulnerability fixes recorded in the [official release history](https://www.7-zip.org/history.txt).
The complete py7zr member graph must pass validation before any native invocation.
Links, junctions, devices, alternate data stream names and portable path collisions
are rejected. Native extraction has a ten-minute timeout, explicitly disables
link and alternate stream options, and must produce exactly the preflighted regular
files and directories, including implicit parent directories. Unexpected entries,
missing entries, special files and hardlinks fail the build. There is no automatic
decoder fallback; selecting a decoder does not establish native runtime acceptance.

The builder checks the upstream SHA-256 before extraction, validates the full
archive member graph, rejects traversal, escaping links, device files and portable
path collisions, and checks copied links again. It writes deterministic sorted
TAR/Zstandard output with normalized timestamps, owners and modes. Executable
intent comes from the recipe and upstream archive metadata, so Windows
cross-packaging preserves POSIX execution permissions. Every regular
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
reads back public release metadata and checksum companions, then downloads and
verifies every public asset again; installed VX
acceptance remains a separate consumer gate.

Optional `release_assets` entries pin original runtime archives and corresponding
source archives by flat asset name, HTTPS URL, SHA-256 and exact byte size. The
workflow retains those bytes alongside the bundles and writes
`release-assets.json` with checksum companions. Local reuse accepts the same pins
and avoids a second download. Conflicting assets fail without overwriting them.
These records preserve the recipe's digest origin; retaining an archive does not
turn a locally computed first-intake hash into an upstream signature.

The verification harness provisions a repository from an independently pinned
index and checks the selected archive plus every regular repository file. From
the builder checkout, use the published index URL and its verified SHA-256:

```bash
vx uv run --locked python -m tools.cache_bundle --index-url "$INDEX_URL" --index-sha256 "$INDEX_SHA256" --tool witr --version 0.3.4 --platform windows --arch x86_64 --cache .cache/rez
vx uv run --locked python -m tools.cache_bundle --index-url "$INDEX_URL" --index-sha256 "$INDEX_SHA256" --tool witr --version 0.3.4 --platform windows --arch x86_64 --cache .cache/rez --offline
```

The second command re-verifies cached content without network access and returns
the repository directory for an SDK consumer. This harness owns no solver or
environment semantics and is separate from installed VX acceptance.

A [catalog](docs/catalog.md) can pin release indices across runtime repositories.
It adds a verified catalog-to-index download chain and exact tool/version lookup;
dependency resolution and environment interpretation remain in Rez Next.
