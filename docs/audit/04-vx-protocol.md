# Audit 04 — Mapping the VX packaging protocol onto the Rez specification

**Question.** VX today defines a private packaging protocol: a `recipe.json`
(`schema/bundle-definition.schema.json`) executed by `tools/build_bundle.py`. The product
direction is *"strategy sinks into `build.py`, the protocol stays Rez's"* — i.e. the same
deterministic packaging should be expressible natively as a Rez `package.py` + `build.py`
built by `rez build`. This audit enumerates every VX-private concept and judges, with
evidence, whether Rez can express it natively.

**Scope.** Evidence-gathering only. No code was modified.

## Evidence base

| Source | Revision | How read |
| --- | --- | --- |
| `vx-org/vx-rez-packages` (this worktree) | `0c493bb` | direct read; all `tools/*.py`, `schema/*.json`, `tests/*.py`, `README.md`, `docs/catalog.md` |
| `vx-org/rez-next` (vendored at `rez-next/`) | `97eef03`, `Cargo.toml version = "0.3.10"` | direct read of `crates/rez-next-build/`, `crates/rez-next-package/`, `crates/rez-next-runtime/` |
| `nerdvegas/rez` (upstream; scratch clone, since deleted) | `f622b81` (master) | direct read of `src/rez/`, `src/rezplugins/`, `docs/source/`; plugin surface cross-checked against the 3.4.0 tag |

Every claim below is cited `file:LINE`. Claims that could not be verified are marked
`UNVERIFIED (reason)`. Nothing is concluded from `README.md` prose alone — where README is
cited it is as a statement of *VX intent*, cross-checked against the code that implements it.

Two naming clarifications used throughout:

- **"upstream Rez"** = `nerdvegas/rez`, the Python reference implementation and the
  specification artifact.
- **"rez-next"** = `vx-org/rez-next`, the Rust reimplementation VX actually ships against.
  rez-next is an *implementation* of the Rez protocol; where the two disagree, the
  disagreement is called out explicitly, because VX's dependency is on rez-next but the
  product hypothesis is about *Rez*.

---

## 1. What the VX protocol actually is

The recipe is a JSON document (`schema/bundle-definition.schema.json`) with 11 top-level
fields and one `$defs` graph. The builder (`tools/build_bundle.py`, 1107 lines) executes it
in a fixed order (`build_bundle()`, `tools/build_bundle.py:86-169`):

1. validate the recipe against the schema and a set of extra path-safety rules
   (`validate_definition`, `:49-67`)
2. select the target triple (`_select_target`, `:301-308`)
3. read, hash-check and AST-validate the pinned `package.py` **without executing it**
   (`_read_package_definition`, `:858-915`)
4. ask the Rez Next SDK for the layout via `installation-plan` (`_installation_plan`,
   `:172-282`)
5. create `package_root`, `variant_root`, `payload_root` from that plan (`:112-119`)
6. download the pinned upstream asset (`_download`, `:321-332`) and verify its SHA-256
   **before** extraction (`_verify_sha256`, `:335-338`, called at `:125`)
7. extract with a full member-graph preflight and apply `payload.mappings`
   (`_install_payload`, `:680-723`)
8. install pinned legal metadata at the package root (`_install_metadata`, `:799-822`)
9. materialise safe internal links as regular content (`_materialize_links`, `:761-796`)
10. synthesise sibling `platform/<p>/` and `arch/<a>/` system packages
    (`_write_system_package`, `:918-923`)
11. emit `manifest.json`, `provenance.json`, `sha256sums.txt` (`:134-151`)
12. run the native smoke test against an isolated copy (`:152-157`, `_smoke_test`
    `:996-1045`)
13. write the deterministic `.rez.tar.zst` (`_write_reproducible_tar_zstd`, `:1048-1074`)

A decisive piece of context: **the VX `package.py` is already valid Rez.** The checked-in
fixture used by rez-next's own test suite (`rez-next/crates/rez-next-runtime/tests/fixtures/witr_package.py`)
is plain Rez — `name`, `version`, `description`, `tools`, `variants` (all six targets),
`commands()` with `env.PATH.prepend("{root}/payload/bin")`. So the *package-side* protocol is
already Rez's; what is private is the **recipe**, the **builder**, and the **release
artifacts**.

---

## 2. Main deliverable — concept-by-concept mapping

`Mappable?` is judged against **upstream Rez** unless the row says otherwise. Where rez-next
diverges, the divergence is named in the last column.

### A. Package identity and definition

| VX private concept | recipe field / builder location | Rez-native equivalent (upstream source path) | Mappable? | Conflict or unmappable part |
| --- | --- | --- | --- | --- |
| Package name | `tool`, schema `:10` | `name` in `package.py` — `src/rez/package_maker.py:54`, `src/rez/package_serialise.py:79` | **YES** | Already duplicated verbatim in the pinned `package.py`. |
| Package version | `version`, schema `:11` | `version` — `src/rez/package_maker.py:56`, `src/rez/package_serialise.py:80` | **YES** | Already duplicated in `package.py`; the builder cross-checks them (`tools/build_bundle.py:883-906`). |
| Hash-pinned `package.py` bytes | `package.definition.{source,sha256}`, schema `:24-27`; `_read_package_definition` `:858-915` | none — Rez *executes* `package.py`; there is no "pin these exact bytes" concept | **NO** | Rez's whole model is a live Python definition. `rez build --install` **regenerates** `package.py` from parsed data via `dump_package_data` (`src/rezplugins/package_repository/filesystem.py:1445-1451`); it never copies the source file (no `shutil.copy` of the definition anywhere in that module). Regeneration drops comments, formatting and any function other than the five `*_commands` blocks. This directly contradicts VX's "copies exactly the same bytes" rule (`README.md:38-44`) and the byte-identity assertion in `tests/test_bundle_contract.py:231`. |
| AST-validate without executing | `_read_package_definition` `:879-914` | none — Rez evaluates the module; rez-next parses a restricted AST subset (`rez-next/crates/rez-next-package/src/python_ast_parser/mod.rs:37-54`) | **NO** | rez-next's parser rejects `for`/`while`/`try`/`with` and non-constant `version` (`mod.rs:306-351`, `:573-586`), which is a *narrower* contract than VX's AST gate, not a Rez-spec one. |
| `description` | `package.description`, schema `:28` | `description` — `src/rez/package_maker.py:58`, `src/rez/package_serialise.py:81` | **YES** | VX never reads it: `grep -rn '"description"' tools/` returns **nothing** — it exists only in test fixtures (`tests/test_bundle_contract.py:81`). Pure restatement of `package.py`. |
| `tools` | `package.tools`, schema `:29` | `tools` — `src/rez/package_maker.py:75`, `src/rez/package_serialise.py:83`; documented `docs/source/package_definition.rst:888-896` | **PARTIAL** | Same name, different semantics. Rez `tools` is a *declaration* — it does not touch the environment; it is consumed only by `ResolvedContext.get_tools()` / `get_tool_variants()` (`src/rez/resolved_context.py:1237-1250`) and by suites. VX `tools` is never read by any tool (`grep '"tools"' tools/` → nothing). It only restates `package.py`. |
| `path_entries` | `package.path_entries`, schema `:30`; consumed at `tools/verify_consumer.py:162-167` | no `path_entries` field — **0 hits repo-wide** in upstream Rez. PATH is set through rex in `commands()`, e.g. `env.PATH.prepend('{root}/payload/bin')` (`src/rez/package_maker.py:81`, `src/rez/rex_bindings.py:273`, fixture `rez-next/crates/rez-next-runtime/tests/fixtures/witr_package.py`) | **PARTIAL** | Rez has no declarative PATH list. The VX acceptance harness builds `PATH` from `path_entries` in declared order and asserts the SDK produces exactly it (`tools/verify_consumer.py:165-167`, `tools/consumer-contract/README.md:25-30`). The real source of truth is `commands()` in `package.py`; the recipe field is a *test expectation* that can silently drift from it. |
| `schema_version` (recipe) | schema `:9` | `format_version` on installed package data — `src/rezplugins/package_repository/filesystem.py:1438` | **PARTIAL** | Different meaning: VX's is the recipe schema; Rez's is the on-disk package-data format. Not the same artifact. |
| `build_revision` (immutable repackaging) | schema `:12`; `expected_release_tag` `:79-83`; tag check `tools/generate_index.py:140-143` | none — Rez has no repackaging revision distinct from package version | **NO** | Would have to become either a version bump (changes Rez package identity) or an arbitrary `package.py` field (see row "arbitrary fields"). |

### B. Target matrix

| VX private concept | recipe field / builder location | Rez-native equivalent (upstream source path) | Mappable? | Conflict or unmappable part |
| --- | --- | --- | --- | --- |
| Target triple matrix | `targets[]`, schema `:66`, `$defs/target` `:88-118` | `variants` — `src/rez/package_maker.py:66`, `src/rez/package_serialise.py:89` | **YES** | `variants = [["platform-windows","arch-x86_64"], ...]` is already exactly what the VX `package.py` declares (6 entries in `rez-next/crates/rez-next-runtime/tests/fixtures/witr_package.py`). `README.md:56-59` states VX does not parse variant requirements itself — the recipe restates them. |
| Variant subpath `platform-<p>/arch-<a>/` | `variant_root` from SDK plan `:117`; asserted `tests/test_bundle_contract.py:376` | `PackageResourceHelper._subpath()` — `src/rez/package_resources.py:493-522`, joined at `src/rezplugins/build_process/local.py:164-166` | **YES (conditional)** | Non-hashed subpath is `os.path.join(*[x.safe_str() for x in self.variant_requires])` → `platform-windows/arch-x86_64`. **Condition: `hashed_variants` must not be `True`.** With `hashed_variants = True` the subpath becomes a SHA-1 hash dir (`package_resources.py:497-517`), which is Rez-legal but breaks every VX path assertion (`tools/cache_bundle.py:93-99`, `schema/bundle-manifest.schema.json:30`). Docs confirm hashing is opt-in: `docs/source/variants.rst:79-104`. |
| `target.triple` (e.g. `x86_64-pc-windows-msvc`) | schema `:92`; used for asset naming `:102`, CI matrix `tools/ci_matrix.py:17-26` | none — Rez has no triple concept | **NO** | Only home is an arbitrary `package.py` field (see below) or the release index (where it already lives, `schema/release-index.schema.json:43`). |
| `target.platform` / `target.arch` | schema `:93-94`; passed to SDK `:194-199` | `platform-<p>` / `arch-<a>` requirement families — `src/rez/system.py:56-62`, `src/rez/bind/os.py:21-22` | **PARTIAL** | **Vocabulary conflict.** Rez's arch comes from `platform.machine()` (`src/rez/utils/platform_.py:120` → `src/rez/system.py:36-43`), which is `AMD64` on Windows and `aarch64`/`arm64` on ARM. VX normalises to `x86_64` and `arm_64` (`tools/build_bundle.py:974-980`, `tests/test_bundle_contract.py:1240-1245`) and ships its own `arch/x86_64/package.py` system package (`_write_system_package` `:918-923`) instead of `rez bind arch`. Rez's native `arch-AMD64` and VX's `arch-x86_64` are different packages. rez-next inherits this: host arch reported as `amd64` / `windows-amd64`. |
| `target.runner` (GH Actions label) | schema `:95`; `tools/ci_matrix.py:22` | none | **NO** | CI metadata, not packaging. Belongs in the workflow, not the protocol. |
| `target.status` (const `supported`) | schema `:96` | none | **NO** | The matrix is *defined by presence* in `variants`; absence is the declaration. |
| `unsupported_targets[]` | schema `:67-74`; echoed into the index `tools/generate_index.py:107` | none | **NO** | A negative declaration with a human `reason`. No Rez home; only the release index (`schema/release-index.schema.json:52-64`). |
| Cross-target build gate (`--triple` must match host) | `_assert_native_target` `:983-993`; invoked `:153` | none — Rez happily builds any declared variant; `rez build --variants INDEX` selects it (`src/rez/cli/build.py:74-77`) | **NO** | VX *forbids* cross-target packaging (`BundleError` at `:989-993`). Rez's model is the opposite: one source tree, N variants, select by index. The gate is a VX policy, not a Rez concept. |

### C. Upstream fetch and integrity

| VX private concept | recipe field / builder location | Rez-native equivalent (upstream source path) | Mappable? | Conflict or unmappable part |
| --- | --- | --- | --- | --- |
| Pinned HTTPS source URL | `target.upstream.url`, schema `:100`; `_download` `:321-332` | **none.** No download primitive exists in upstream Rez: `grep -rn "urlopen\|urllib\|requests\." src/rez/` (excluding `vendor/`) returns only `urllib.parse` inside `src/rez/utils/amqp.py` | **NO (spec-level)** | Fetching is by convention the build script's job. This is *strategy*, so "sinks into `build.py`" works — but there is no Rez protocol statement of it either way. |
| HTTPS enforcement incl. redirect hops | `_download` `:328-329` | none | **NO** | No Rez network layer to enforce it on. |
| SHA-256 verification of the fetched asset | `target.upstream.sha256`, schema `:101`; `_verify_sha256` `:335-338`, called `:125` | **none.** No integrity primitive anywhere in upstream Rez: `grep -rn "sha256\|checksum\|hashlib" src/rez/` (excluding `vendor/`) yields only `sha1` (variant hashing `src/rez/package_resources.py:23`, cache/order keys) and `md5` (`src/rez/utils/memcached.py:15`) | **NO (spec-level)** | **This is the single largest specification gap.** A Rez package definition cannot state "my payload is this byte sequence". rez-next has SHA-256 — but only inside `binary_archive`, driven by env vars, not by any package field (`rez-next/crates/rez-next-build/src/systems/binary_archive.rs:20`, `:123-125`, `:210-232`). |
| Hash-pinned legal metadata | `metadata[]`, schema `:45-52`; `_install_metadata` `:799-822` | none | **NO** | Just payload files once installed; the *pin* is recipe-side only. |
| Upstream provenance (repo / revision / licence / source URL / source SHA-256) | `provenance`, schema `:34-44`; written to `provenance.json` `:135-149` | **PARTIAL — different subject.** Rez has `revision`, `changelog`, `release_message`, `previous_version`, `previous_revision`, `authors`, `uuid` (`src/rez/package_serialise.py:109-113`), populated by `rez release` from the *recipe's* VCS (`src/rez/cli/release.py:56-142`) | **PARTIAL** | Rez's fields describe the **recipe repository's** VCS state. VX's describe the **third-party upstream project** (`provenance.repository`, `provenance.revision`, `provenance.source_url`, `provenance.source_sha256`). There is no Rez field that carries an upstream source digest. Closest available home: an arbitrary `package.py` field. |
| `upstream_manifest` (upstream SHA256SUMS URL) | schema `:14`; echoed into `manifest.json` `:939` | none | **NO** | |
| `compatibility.{rez_next, vx_rez_adapter}` | schema `:15-19`; `schema/bundle-manifest.schema.json:51-59` | `requires_rez_version` — `src/rez/package_maker.py:52` | **PARTIAL** | `requires_rez_version` covers the Rez half. There is no Rez concept for "which *implementation*" or for a separate adapter crate. |
| `release_assets[]` (retained original archives, byte size + digest) | schema `:53-65`; `tools/retain_release_assets.py:54-74`, `:81-91` | none | **NO** | Pure release-distribution concern; `size` + `sha256` pins have no package-definition home. |
| Arbitrary `package.py` attributes as the metadata escape hatch | — (`Optional(str): object` is the Rez mechanism, not a VX one) | canonical field list `src/rez/package_resources.py:123-182`, ending with the catch-all `Optional(str): late_bound(object)` at `:173`; `src/rez/package_maker.py:92` / `src/rez/package_serialise.py:115` end the same way; `dump_package_data` preserves unknown keys (`src/rez/package_serialise.py:143-146`); `Package.arbitrary_keys()` exposes them (`src/rez/packages.py:232-240`) | **YES (mechanism exists)** | **rez-next does not honour it.** Unknown top-level assignments are parsed into `PackageData.extra_fields` but never copied onto `Package` (`rez-next/crates/rez-next-package/src/python_ast_parser/mod.rs:296-300`; `Package` has no such field, `rez-next/crates/rez-next-package/src/package/types.rs:10-88`). So the natural Rez home for VX's orphan fields is **silently dropped** by the implementation VX actually targets. |
| Build-only fields are stripped at install | — | `src/rez/package_resources.py:42-48` — `requires_rez_version`, `build_system`, `build_command`, `preprocess`, `pre_build_commands` are not part of the installed schema | **N/A (positive)** | Useful: a `build.py`-driven package installs a clean definition — the build strategy does not leak into the published `package.py`. This is the one place where Rez's model already matches "strategy sinks into `build.py`". |

### D. Payload materialisation

| VX private concept | recipe field / builder location | Rez-native equivalent (upstream source path) | Mappable? | Conflict or unmappable part |
| --- | --- | --- | --- | --- |
| Archive format `binary\|zip\|tar\|tar.zst\|7z` | `payload.format`, schema `:105`; dispatch `_extract_archive` `:580-695` | none upstream. rez-next `binary_archive` supports **only `.zip` and `.tar.gz`/`.tgz`** (`rez-next/crates/rez-next-build/src/systems/binary_archive.rs:234-251`) | **NO** | `binary` (raw file), plain `tar`, `tar.zst` and `7z` all hit the `else` arm → `"unsupported binary archive format"` (`binary_archive.rs:246-249`). `tar.zst` is required by the `python` recipe; `7z` and `binary` by others. No zstd or 7z dependency in `rez-next/crates/rez-next-build/Cargo.toml`. |
| Decoder selection (`py7zr` / `native-7zip`) | `payload.decoder`, schema `:106`; `:466-517` | none | **NO** | |
| Per-file source→destination mappings | `payload.mappings[]`, schema `:107-113`; `_install_payload` `:706-721` | none. rez-next has a *single directory selector*, `REZ_BINARY_ARCHIVE_PAYLOAD_PREFIX` (`binary_archive.rs:19-22`, `:128-138`) | **NO** | The prefix var selects **one directory inside the archive** and requires it to exist (hard error otherwise). It cannot express N independent mappings, renames, or `binary` single-file installs. |
| Prefix stripping | implicit in `mappings[].source`; `:707` | `REZ_BINARY_ARCHIVE_PAYLOAD_PREFIX` (rez-next, `binary_archive.rs:128-131`) | **PARTIAL** | rez-next's is "pick one subdir", VX's is "map N paths, stripping arbitrary prefixes". |
| Declared executable intent | `mappings[].executable`, schema `:111`; applied `:689`, `:717-721`; packed `:1057` | none — Rez has no declarative file-mode field | **NO** | rez-next preserves Unix modes from zip entries only, under `#[cfg(unix)]` (`binary_archive.rs:283-292`); nothing sets an exec bit on Windows. VX's whole point is that Windows cross-packaging preserves POSIX exec intent (`README.md:98-101`). |
| `payload/` subdirectory under the variant root | `payload_root` `:118`; `schema/bundle-manifest.schema.json:30`; asserted `tools/cache_bundle.py:93-99` | **none — and mildly opposed.** Rez's "payload" *is* the package version dir: `get_package_payload_path` returns `<location>/<name>/<version>` (`src/rezplugins/package_repository/filesystem.py:1026-1034`), consumed as the install path (`src/rez/build_process.py:241-252`) | **NO** | Not a conflict in the sense of being illegal — files may be laid out anywhere under the variant root; `commands()` then references `{root}/payload/bin`. But nothing in Rez produces or expects a `payload/` level, and `binary_archive` installs straight into the variant root (`binary_archive.rs:106`, `:309-336`). |
| Sibling `platform/<p>/` and `arch/<a>/` system packages | `_write_system_package` `:918-923`; asserted `tests/test_bundle_contract.py:213-214` | `rez bind platform arch os` — `src/rez/bind/os.py:14-26` | **YES** | Rez's bound `arch` family is `arch-AMD64` on Windows, not `arch-x86_64` (see row "target.arch"). VX synthesising its own is what makes the vocabulary divergence invisible. |
| Link materialisation (symlink → regular content) | `_materialize_links` `:761-796`; `_audit_links` `:750-758` | none — and **inverted**: Rez *creates* symlinks for variant shortlinks (`src/rezplugins/build_process/local.py:194-208`) | **NO** | VX requires a zero-symlink repository (`tools/cache_bundle.py:126`), which is what makes bundles portable and fully hashed. Rez's shortlink feature only activates with `hashed_variants = True`, so there is no direct clash — but Rez has no concept of "flatten links for portability". |
| Directory aliases (duplicated framework resources) | `_materialize_links` `copy_resolved` `:774-784` | none | **NO** | |
| `installation-plan` SDK dependency (layout authority) | `_installation_plan` `:172-282`; required `:180-184` | **none upstream.** This is a rez-next-only command: `rez-next/crates/rez-next-runtime/src/installation_plan.rs`, exposed by the `rez-next-runtime` binary (`rez-next/crates/rez-next-runtime/src/bin/rez-next-runtime.rs:20-37`) | **NO (rez-next-private)** | VX deliberately refuses to infer layout (`README.md:48-54`, docstring `tools/build_bundle.py:179`). The equivalent Rez fact is computed locally by `_subpath` (`src/rez/package_resources.py:493-522`) — i.e. upstream Rez needs no such RPC. Once VX targets Rez natively, this dependency becomes unnecessary; it is currently a hard build-time requirement, not a protocol concept. |

### E. Determinism and release artifacts

| VX private concept | recipe field / builder location | Rez-native equivalent (upstream source path) | Mappable? | Conflict or unmappable part |
| --- | --- | --- | --- | --- |
| Deterministic `tar.zst` (sorted walk, uid/gid 0, `uname`/`gname` empty, `mtime` = release epoch, mode 0755/0644/0777, PAX, zstd level 10, `threads=0`) | `_write_reproducible_tar_zstd` `:1048-1074` | **none.** No reproducibility primitive exists in upstream Rez or in rez-next | **NO (spec-level)** | Proof that determinism is entirely a property of the *pack writer*, not of the content: `tests/test_bundle_contract.py:176-228` touches the source (`:178`) and patches `tarfile.gettarinfo` to force mode 0644 (`:181-186`), then asserts byte-identical archives both times (`:179`, `:188`). Nothing in Rez's install path sorts walks or normalises mtime/uid/gid/mode; rez-next's `copy_tree_contents` iterates raw `fs::read_dir` (`binary_archive.rs:312`) and `fs::copy` (`:358`) does not preserve mtimes. |
| `build_time` / timestamp determinism | `release_date` → epoch `:1051` | `timestamp` (int, seconds) — `src/rez/package_serialise.py:108`; written at install `src/rezplugins/package_repository/filesystem.py:1433-1435`; **overridable** | **PARTIAL** | Rez's `timestamp` is overridable, but only through `install_variant(overrides={"timestamp": N})` — overrides merge at `src/rezplugins/package_repository/filesystem.py:1423-1431`, *before* the default at `:1433-1435`; and **for an already-existing package the existing value wins** (`:1424-1426`). Two further limits: (a) it is package *metadata*, not filesystem mtime; (b) there is no determinism *switch* — `SOURCE_DATE_EPOCH` is 0 hits repo-wide (only in vendored `distlib`, which rez never reads), `rez build` has no `--timestamp` flag (all flags enumerated at `src/rez/cli/build.py:43-110`) and there is no config setting. The release path does set it (`src/rezplugins/build_process/local.py:444-446`). rez-next models the field (`rez-next/crates/rez-next-package/src/package/types.rs:57-58`) and consumes it in filters, yet **nothing in its build or release path ever sets it**. |
| `sha256sums.txt` over every regular repository file except itself | `_write_repository_checksums` `:965-971`; scope string `:946`; enforced `tools/cache_bundle.py:108-127` | none | **NO (spec-level)** | The "complete file set" invariant (`actual != declared` → fail, `tools/cache_bundle.py:126-127`) has no Rez analogue. Rez's only package-file integrity surface is `PackageMetadata.checksum` in rez-next, which is unwired to the build path. |
| `manifest.json` | `_bundle_manifest` `:926-949`; `schema/bundle-manifest.schema.json` | none | **NO** | Carries `payload_root`, `upstream.*`, `checksums.scope`, `compatibility` — all VX consumer-contract fields. |
| `provenance.json` | `:135-149` | partially: `revision`/`changelog`/`release_message` (`src/rez/package_serialise.py:109-113`) | **PARTIAL** | VX's file additionally pins the whole recipe (`recipe_sha256`, `:145-147`), the SDK plan (`:142`) and the release tag (`:144`). No Rez home. |
| `THIRD_PARTY_NOTICES.txt` | via `metadata[]`; generated by `tools/collect_notices.py:13-38` | none | **NO** | Just a payload file once installed; the *generation* contract (unedited texts, upstream-relative paths) is VX's. |
| Bundle asset naming `<tool>-<version>-<triple>.rez.tar.zst` | `:102`; `schema/release-index.schema.json:44` | none | **NO** | Release-artifact naming, not package identity. |

### F. Tests

| VX private concept | recipe field / builder location | Rez-native equivalent (upstream source path) | Mappable? | Conflict or unmappable part |
| --- | --- | --- | --- | --- |
| Smoke command | `package.smoke_test.command` / `target.smoke_test.command`, schema `:79-87`, `:97`; executed `:1003-1040` | `tests = {"smoke": {"command": [...], "requires": [...], "on_variants": True}}` — schema `src/rez/package_resources.py:101-121` (hooked `:154`) and `src/rez/package_maker.py:32-49`; runner `src/rez/package_test.py`; CLI `src/rez/cli/test.py`; documented `docs/source/package_definition.rst:833-886` | **YES** | Test command strings expand package attributes such as `{root}` (`docs/source/package_definition.rst:838-840`), which is the same mechanism as VX's `{root}`/`{version}`/`{exe}` substitution (`tools/build_bundle.py:997-1003`). |
| Expected-output assertion (`expect` substring in stdout+stderr) | schema `:81`; `:1043-1045` | **none.** `src/rez/package_test.py` has no `expect` and no stdout assertion — only exit status | **NO (spec-level)** | |
| `timeout_seconds` | schema `:85`; `:1037`; doubled by the harness `tools/verify_consumer.py:215` | none (`grep -rn timeout src/rez/package_test.py` → no hits) | **NO** | |
| Per-variant test selection | `target.smoke_test` overrides package level, `:1002` | `on_variants` / `requires` in the `tests` entry — `src/rez/package_maker.py:32-49`; filtering `src/rez/package_test.py:314-336`, `:499`, `:523` | **YES** | `on_variants: True` runs the test on **all** variants, which is exactly VX's per-target smoke matrix (`docs/source/package_definition.rst:851-853`). |
| Isolated test copy | smoke runs against a private copy of the package, `:154-157` | `_run_tests` installs the variant into a temporary testing repository and runs the test against a temp variant whose root is patched to the real payload — `src/rezplugins/build_process/local.py:451-462` (docstring), `:474-493` | **YES** | Upstream isolates the *package under test*; VX additionally isolates the *process environment* (see next row). |
| Hermetic process environment (isolated HOME/APPDATA/XDG/TMP, `PYTHONHOME`/`PYTHONPATH` stripped) | `:1010-1031` | none — Rez runs the test inside a *resolved Rez context*, which is additive, not hermetic | **NO** | Different philosophy: Rez composes an environment; VX isolates one. Nothing in `src/rez/package_test.py` touches `HOME`, `XDG_*`, `APPDATA` or `PYTHONHOME`. |
| Test at build time | not part of `rez build` for VX — run by the workflow, `.github/workflows/runtime-release.yml:98` | upstream: **yes, tag-gated** — `run_on: ["pre_install"]` runs before `rez build -i` and aborts the install on failure (`src/rezplugins/build_process/local.py:373-382`, `_run_tests` `:449-508`); `run_on: ["pre_release"]` gates release (`:427-436`). `rez-next:` runs `package.tests` unconditionally (`rez-next/crates/rez-next-build/src/process.rs:556-624`) | **PARTIAL** | The two implementations disagree on *gating*, not on existence. Upstream's `run_on` vocabulary is `default` / `pre_install` / `pre_release` / `explicit` (`docs/source/package_definition.rst:844-848`); failure deletes the installed payload and aborts (`:380-382`). rez-next sorts tests by name (`process.rs:599-600`), substitutes `{root}`/`{base}` (`:601-606`), and its AST parser **rejects** the structured form outright (`rez-next/crates/rez-next-package/src/python_ast_parser/mod.rs:646-666`), so no upstream-compatible `run_on` declaration survives. |

### G. Distribution (out of protocol scope, listed for completeness)

| VX private concept | location | Rez-native equivalent | Mappable? | Note |
| --- | --- | --- | --- | --- |
| Release index | `schema/release-index.schema.json`; `tools/generate_index.py` | none | **NO** | Rez resolves packages from a *repository path*, not from an HTTPS index of archives. This is VX distribution, not packaging. |
| Catalog | `schema/catalog.schema.json`; `tools/catalog.py` | none | **NO** | Same. `docs/catalog.md:60-65` states the catalog owns no solver or environment semantics by design. |
| `.rez.tar.zst` as a directly extractable repository | `_write_reproducible_tar_zstd` `:1048`; `tools/cache_bundle.py:132-161` | Rez repositories are directories; `rez-copy`/`package_cache` are the transport | **NO** | A "repository-as-archive" transport has no upstream counterpart. |

---

## 3. Summary counts

53 concept rows were assessed (plus one row that is a positive finding rather than a mapping).

| Verdict | Count | Concept groups |
| --- | --- | --- |
| **YES** | 10 | `name`, `version`, `description`, `variants` matrix, `platform-<p>/arch-<a>` subpath (non-hashed), arbitrary `package.py` attributes, `rez bind platform/arch`, smoke command, per-variant test selection, isolated test copy |
| **PARTIAL** | 10 | `tools` semantics, `path_entries`, `schema_version`, `platform`/`arch` families (vocabulary), upstream provenance (different subject), `compatibility`, prefix stripping, `timestamp` (metadata only), `provenance.json`, build-time test invocation |
| **NO** | 33 | see breakdown below |

The 33 `NO` rows are **not** equally blocking. Only six are specification gaps:

| Kind of `NO` | Count | Rows | What it means for the migration |
| --- | --- | --- | --- |
| **Build strategy** | 11 | pinned URL, HTTPS enforcement, hash-pinned legal metadata, all five payload formats, `decoder`, per-file mappings, declared executable intent, `payload/` level, link materialisation, directory aliases, `THIRD_PARTY_NOTICES.txt` | **Not blocking.** No Rez protocol statement is needed — the script just does it. These are precisely the concepts that "sink into `build.py`". |
| **VX policy / CI / distribution** | 12 | `build_revision`, `triple`, `runner`, `status`, `unsupported_targets`, cross-target gate, `upstream_manifest`, `release_assets`, bundle asset naming, release index, catalog, repository-as-archive | **Not blocking.** Not packaging protocol at all. They belong to the release workflow and the distribution index, where several already live. |
| **Specification gap** | 6 | **SHA-256 verification**, **deterministic archive**, **`sha256sums.txt`**, **`manifest.json`**, **`expect`**, **`timeout_seconds`** | **Blocking.** Escalated in the verdict below. |
| **Impedance mismatch with Rez's model** | 3 | hash-pinned `package.py` bytes, AST-validate-without-executing, `installation-plan` SDK dependency | Needs a product decision: Rez executes (or re-serialises) the definition and computes layout locally, so VX's "never execute, never regenerate, never infer" rules have to become explicit policy rather than protocol. |
| **Environment philosophy** | 1 | hermetic process environment for tests | Rez composes an environment; VX isolates one. Needs a decision about whether the isolation is a VX requirement or an artifact of the current harness. |

---

## Verdict on the product hypothesis

> *Can deterministic/reproducible packaging be expressed entirely in Rez-native terms via
> `binary_archive` + `variants` + `build.py`?*

**No — and the split is clean enough to act on.**

### What is already Rez's (requiring no new protocol)

The package-side protocol is Rez's today. The checked-in `package.py` is valid Rez
(`rez-next/crates/rez-next-runtime/tests/fixtures/witr_package.py`): `name`, `version`,
`description`, `tools`, a six-entry `variants` list, and `commands()` with
`env.PATH.prepend("{root}/payload/bin")`. The published layout is Rez's layout:

```text
witr/0.3.4/platform-windows/arch-x86_64/payload/bin/witr.exe
```

is `<repo>/<name>/<version>/<variant-subpath>/<files>`, produced by upstream Rez as
`os.path.join(package_install_path, subpath)` where `subpath` is the non-hashed join of the
variant requirements (`src/rezplugins/build_process/local.py:164-166` +
`src/rez/package_resources.py:493-522`). The `package.py` at `<name>/<version>/package.py` is
Rez's default `package_filenames = ["package"]` (`src/rezplugins/package_repository/rezconfig.py:45-47`).
The sibling system packages are `rez bind platform arch` (`src/rez/bind/os.py:14-26`).

**Therefore: package construction — download → verify → strip prefix → map into `payload/`
under the variant root — is fully expressible as a Rez `build.py`.** Upstream Rez's vehicle
is `build_system = "custom"` + `build_command`, with `{root}`, `{install}`, `{install_path}`,
`{build_path}`, `{name}`, `{version}`, `{variant_index}` expansion
(`src/rezplugins/build_system/custom.py:44-54`, `:148-161`). rez-next's vehicle is
`build_system = "build.py"`, executed via `runpy` with argv `build`/`install`/`test`.
Both are the *same* protocol statement: "run my script, hand it the variant root".

Two cautions on that vehicle:

- **`build_system = "build.py"` is not portable to upstream Rez.** Upstream resolves that
  string through the plugin manager (`src/rez/build_system.py:115`,
  `plugin_manager.get_plugin_class('build_system', buildsys_type)`) and ships only
  `cmake`, `make`, `custom` (`ls src/rezplugins/build_system/`; `make` is in fact
  non-functional — `MakeBuildSystem.__init__` raises `NotImplementedError`,
  `src/rezplugins/build_system/make.py:24`). `binary_archive` does not exist upstream at all
  (`grep -rn binary_archive` across the tree → 0 hits). The "any unrecognised name becomes a
  script file" behaviour is a rez-next extension.

  **The portable spelling is already the upstream convention.** Seven of upstream Rez's own
  build test fixtures declare exactly
  `build_command = 'python {root}/build.py {install}'` — e.g.
  `src/rez/data/tests/builds/packages/foo/1.0.0/package.py:17`,
  `.../bah/2.1/package.py:15`, `.../loco/3/package.py:10` — using the `build_command` field
  declared at `src/rez/package_maker.py:88`. Upstream Rez has no `post_build.py`; the only
  build hook is the in-package `pre_build_commands()` function
  (`src/rez/package_resources.py:51-57`). And because `build_system` / `build_command` /
  `preprocess` are stripped from the installed schema (`src/rez/package_resources.py:42-48`),
  the strategy genuinely does not leak into the published definition.
- **`binary_archive` alone is not sufficient**, and this is implementation-level, not
  spec-level: it accepts only `.zip`/`.tar.gz`/`.tgz`
  (`rez-next/crates/rez-next-build/src/systems/binary_archive.rs:234-251`), offers one
  directory selector rather than N mappings (`:128-138`), installs into the variant root
  rather than a `payload/` level (`:106`, `:309-336`), and has no declarative configuration
  surface at all — its four inputs are environment variables (`:19-22`).

### What cannot be expressed, and why

**The release half has no Rez-native home.** Not one of these has an upstream counterpart:

- deterministic/reproducible archive output (`_write_reproducible_tar_zstd`,
  `tools/build_bundle.py:1048-1074`);
- `sha256sums.txt` over the complete repository file set (`:965-971`);
- `manifest.json` (`:926-949`);
- `provenance.json` (`:135-149`).

This is not an oversight in VX's mapping — it is absent by construction. There is no
reproducibility primitive (no `SOURCE_DATE_EPOCH`, no mtime/uid/gid/mode normalisation, no
sorted walk) in either `nerdvegas/rez` or `vx-org/rez-next`. There is no per-file checksum
manifest in the Rez repository contract. And there is no integrity primitive at all in
upstream Rez: `grep -rn "sha256\|checksum\|hashlib" src/rez/` (excluding vendored code)
returns only `sha1` for variant hashing and `md5` for memcached keys.

`tests/test_bundle_contract.py:176-228` settles the locus of determinism empirically:
touching the source and forcing every host mode to 0644 both still yield byte-identical
archives. Determinism is produced by the pack writer alone, after Rez is finished.

### The specification-layer gap (for product adjudication)

Per the audit brief, **no VX-side private fallback is proposed.** The gap is stated as a
Rez-specification gap. Of the six specification-gap rows in section 3, four collapse into
the two structural gaps below, and two are narrow test-schema gaps.

**Gap 1 — the Rez packaging protocol has no integrity model.**
A Rez package definition cannot assert anything about the bytes it will contain. There is no
`sha256`, no source pin, no checksum step in the build pipeline. VX's entire supply-chain
posture — verify the upstream digest *before* extraction (`tools/build_bundle.py:125`),
verify the pinned `package.py` bytes *before* anything else (`:263-264`, proven by
`tests/test_bundle_contract.py:255`, `:264`), verify every metadata file (`:810`), verify
every repository file against `sha256sums.txt` before use (`tools/cache_bundle.py:108-127`)
— is built on a primitive Rez does not define. Moving the *strategy* into `build.py` is
possible and desirable; the *protocol statement* "this package is these bytes" has no home.

**Gap 2 — the Rez packaging protocol has no reproducibility model.**
Rez records `timestamp` as overridable package metadata
(`src/rez/package_serialise.py:108`, `src/rezplugins/package_repository/filesystem.py:1433-1435`),
but nothing in Rez's build or install path normalises file mtimes, owners, or modes, sorts
directory walks, or emits a canonical archive. A Rez repository is a directory, not an
artifact: it has no byte-identity to be reproducible. VX's published contract is a
byte-identical, digest-pinned, directly extractable archive
(`tests/test_bundle_contract.py:176-228`; `tools/cache_bundle.py:132-161`).

Two narrower gaps, same class, smaller blast radius: the `tests` schema carries no
expected-output assertion and no timeout (`src/rez/package_resources.py:101-121`,
`src/rez/package_test.py`), so VX's `expect` substring and `timeout_seconds`
(`tools/build_bundle.py:1043-1045`, `:1037`) have nowhere to go. Both are expressible as
build-script behaviour; they are listed as specification gaps only because a *declared*
test expectation would let a Rez consumer re-run the check.

One secondary conflict also belongs here rather than in an implementation tracker:

**Gap 3 — `rez build --install` regenerates `package.py` instead of preserving it.**
Upstream writes the installed definition via `dump_package_data`
(`src/rezplugins/package_repository/filesystem.py:1445-1451`), which re-serialises parsed
data and drops comments, formatting and any function outside the five `*_commands` blocks.
VX's contract is the opposite and explicit: "copies exactly the same bytes into the bundle …
No package definition is generated as a fallback" (`README.md:38-44`). rez-next's *release*
path happens to byte-copy (`rez-next/crates/rez-next-build/src/release.rs:589-591`), but its
plain build path does not, and upstream Rez does not in any path. "The definition you
installed is the definition that was reviewed" is not a Rez guarantee.

**Net.** The product hypothesis holds for **construction** and fails for **release**. VX can
delete the private *recipe-as-protocol* layer and let `package.py` + `build.py` carry
everything Rez carries. It cannot express its published artifact contract in Rez terms, and
per the audit brief that is escalated as a specification-layer question rather than solved
locally.

---

## Migration direction

| Concept group | Direction | Justification |
| --- | --- | --- |
| Package identity (`name`, `version`, `description`, `tools`) | **MAPPABLE NOW** | Already declared in the pinned `package.py`; the recipe only restates them (`tools/build_bundle.py:883-906`). |
| Pinned `package.py` bytes + AST gate + never-execute | **NEEDS SPEC-LAYER WORK** | Rez executes the definition and upstream regenerates it at install (`src/rezplugins/package_repository/filesystem.py:1445-1451`); "pin these bytes" is not a Rez concept (Gap 3). |
| Target matrix → `variants` | **MAPPABLE NOW** | The VX `package.py` already declares all six variants; `platform-<p>/arch-<a>` is Rez's non-hashed subpath (`src/rez/package_resources.py:493-522`). |
| `hashed_variants` | **NEEDS PRODUCT DECISION** | Must stay `False`/unset or every VX path assertion breaks; Rez treats hashing as opt-in (`docs/source/variants.rst:79-104`) and shortlinks would violate the zero-symlink invariant (`tools/cache_bundle.py:126`). |
| `triple`, `runner`, `status`, `unsupported_targets` | **NEEDS PRODUCT DECISION** | Pure VX/CI metadata with no Rez home; either drop to the release index (where `triple` already lives) or admit them as arbitrary `package.py` fields. |
| `platform`/`arch` families | **NEEDS SPEC-LAYER WORK** | Rez's arch vocabulary is host-derived from `platform.machine()` (`src/rez/utils/platform_.py:120`): `AMD64` on Windows, `aarch64` on ARM. VX uses `arch-x86_64` / `arch-arm_64` (`tools/build_bundle.py:974-980`). No canonical Rez vocabulary exists to map onto. |
| Pinned URL + HTTPS enforcement | **MAPPABLE NOW** | Fetch strategy belongs in `build.py`; Rez has no network layer, so nothing conflicts. |
| SHA-256 verification (as build strategy) | **MAPPABLE NOW** | `verify_sha256` is available to `build.py` via `rez_next.build_plugins`; ordering ("verify before extract", `tools/build_bundle.py:125`) is the script's business. |
| SHA-256 verification (as a protocol statement) | **NEEDS SPEC-LAYER WORK** | No Rez package field can declare a payload digest (Gap 1). |
| Payload formats, `decoder`, per-file mappings, declared exec intent, `payload/` level | **MAPPABLE NOW** (in `build.py`) | All build strategy; the script controls destination and modes outright. |
| …same, via `binary_archive` | **NEEDS SPEC-LAYER WORK** | rez-next's `binary_archive` supports 2 of 5 formats, one directory selector, no `payload/` level, no exec intent on Windows, and env-var-only config (`binary_archive.rs:19-22`, `:128-138`, `:234-251`, `:283-292`). |
| Link materialisation, directory aliases | **MAPPABLE NOW** (in `build.py`) | `copy_tree_contents` already copies symlink content (documented `README` of the contract); the zero-symlink invariant is then just an assertion. |
| Sibling `platform/`, `arch/` system packages | **MAPPABLE NOW** | `rez bind platform arch` (`src/rez/bind/os.py:14-26`) — modulo the arch vocabulary above. |
| `installation-plan` dependency | **MAPPABLE NOW** (droppable) | Layout is computed locally by `_subpath` in upstream Rez; the RPC exists only because VX refuses to infer layout (`tools/build_bundle.py:179`). |
| Deterministic `tar.zst`, `sha256sums.txt`, `manifest.json`, `provenance.json` | **NEEDS SPEC-LAYER WORK** | No reproducibility or per-file-manifest concept exists in either implementation (Gap 2). |
| `release_date` → `timestamp` | **NEEDS SPEC-LAYER WORK** | `timestamp` is overridable (`src/rezplugins/package_repository/filesystem.py:1433-1435`) and rez-next models it (`rez-next/crates/rez-next-package/src/package/types.rs:57-58`) but never sets it — and it is metadata, not file mtime. |
| Smoke command, per-variant selection, build-time gating, isolated test copy | **MAPPABLE NOW** | `tests = {"smoke": {"command": [...], "on_variants": True, "run_on": ["pre_install"]}}` — declaration `docs/source/package_definition.rst:833-886`, build wiring `src/rezplugins/build_process/local.py:373-382`, temp-repository isolation `:451-462`. Failure deletes the payload and aborts the install (`:380-382`), which is a stricter gate than VX's workflow-level smoke. |
| `expect`, `timeout_seconds`, hermetic process env, native-target gate | **NEEDS SPEC-LAYER WORK** | Rez asserts exit status only — no stdout assertion and no timeout anywhere in `src/rez/package_test.py`; nothing touches `HOME`/`XDG_*`/`APPDATA`/`PYTHONHOME`; and Rez has no rule forbidding a build for a non-host variant. |
| `build_revision` | **NEEDS PRODUCT DECISION** | Either a version bump (changes Rez identity) or an arbitrary field; Rez has no repackaging-revision concept. |
| `release_assets`, release index, catalog | **NEEDS PRODUCT DECISION** | Distribution-layer concerns outside the packaging protocol (`docs/catalog.md:60-65` already disclaims solver/env semantics). |

---

## Candidate GitHub issues

### Belongs on `vx-org/rez-next` (implementation defects in the Rez reimplementation)

**1. `binary_archive`: support `tar.zst`, `7z`, plain `tar`, and raw binary artifacts**

```
`binary_archive` dispatches purely on the lowercased filename suffix and supports only
`.zip`, `.tar.gz` and `.tgz`; everything else fails with "unsupported binary archive
format" (`crates/rez-next-build/src/systems/binary_archive.rs:234-251`).

Real Rez packages ship prebuilt payloads as bare binaries, `.tar`, `.tar.zst` and `.7z`
(the vx-rez-packages `witr` recipe uses `zip` on Windows and `binary` elsewhere; the
`python` recipe uses `tar.zst`). None of those can be built today.

The crate has no zstd or 7z dependency (`crates/rez-next-build/Cargo.toml`). Please add
at least zstd and plain-tar arms, and a raw-file passthrough for single-binary artifacts.
A content-sniffing fallback would be preferable to suffix matching.
```

**2. Unknown `package.py` attributes are parsed and then silently discarded**

```
Upstream Rez ends both `package_maker.package_schema` and `package_serialise_schema` with
`Optional(str): object`, preserves those keys through `dump_package_data`
(`src/rez/package_serialise.py:115`, `:143-146`) and exposes them via
`Package.arbitrary_keys()` (`src/rez/packages.py:232-240`). This is the standard Rez
escape hatch for package metadata.

rez-next parses unknown top-level assignments into `PackageData.extra_fields`
(`crates/rez-next-package/src/python_ast_parser/mod.rs:296-300`) but never copies them
onto `Package`, which has no such field
(`crates/rez-next-package/src/package/types.rs:10-88`). A package that sets
`vx_upstream_sha256 = "..."` builds successfully and the attribute vanishes.

Either propagate `extra_fields` onto `Package`, or emit a warning naming the dropped
attributes. Silent loss of package metadata is the worst of the three outcomes.
```

**3. `REZ_BUILD_TARGET_PLATFORM` / `_ARCH` / `_OS` are read but never set**

```
`BuildContext` reads `REZ_BUILD_TARGET_PLATFORM`, `REZ_BUILD_TARGET_ARCH` and
`REZ_BUILD_TARGET_OS`, but no code path ever assigns them. They are always unset and the
context silently falls back to the host, so `target_platform` reports `windows-amd64` and
`target_arch` reports `amd64` even when a different variant was selected.

Consequence: a cross-target build silently believes it is building for the host, and the
installed variant subpath is computed from host values.

Please set all three on the build path from the selected variant (or document that the
caller must inject them, and fail loudly when they are absent).
```

**4. Host architecture `amd64` does not match the `arch-x86_64` package family**

```
`platform.machine()` yields `AMD64` on Windows while the Rez package family produced by
`rez bind os` for x86_64 Linux/macOS is `arch-x86_64`. rez-next reports the host arch as
`amd64` and the target platform as `windows-amd64`, neither of which is a valid package
requirement against `arch-x86_64`.

Any code mapping `target_arch` into a variant requirement needs a private translation
table today. Please normalise to one canonical vocabulary (and cover `aarch64` vs
`arm64`) and expose it as a supported function rather than leaving each caller to guess.
```

**5. `rez build --install` does not install `package.py`; the release path does**

```
The release path byte-copies the source definition
(`crates/rez-next-build/src/release.rs:589-591`), but the plain build path leaves the
variant root containing only the payload — `package.py` is never written.

A package installed via `rez build --install` is therefore not loadable from the
repository it was installed into. Please either write the definition on the build path
too, or document the split explicitly so callers stop working around it.
```

**6. `build_system = "custom"` silently degrades to a copy-only no-op**

```
`create_build_system("custom")` resolves to `Custom("default")`, which is a copy-only
build: the user's build script is never executed and the build reports success. A
plausible-looking `package.py` no-ops with no diagnostic.

Please at minimum warn when `custom` resolves to a magic token with no `build_command`
set, and document that a script file must be named directly
(`build_system = "build.py"`).
```

**7. Build-script child environment is cleared and `PATH` is not restored**

```
The child environment handed to a `build.py` is cleared; on Windows only `TEMP`, `TMP`
and `SystemRoot` are restored, and `PATH` is absent entirely. Any build script that
shells out (`7z`, `git`, `curl`, `tar`) fails with a confusing error.

Upstream Rez's `custom` build system runs the command inside a resolved context, so
`PATH` is populated. Please restore `PATH` — or document the exact set of variables a
build script may rely on.
```

**8. Structured `tests` entries are rejected by the `package.py` parser, and `run_on` gating is absent**

```
Upstream Rez accepts `tests = {"smoke": {"command": [...], "requires": [...],
"run_on": [...], "on_variants": ...}}` (`src/rez/package_maker.py:32-49`).

rez-next's AST parser accepts only the flat `{"name": "shell command"}` form and errors
with "Unsupported test definition" on the structured form
(`crates/rez-next-package/src/python_ast_parser/mod.rs:646-666`). Separately,
`extract_tests_from_package` hardcodes `requires: []`, `run_on: ["default"]` and
`on_variants: None`, so `TestDefinition.requires` / `run_on` / `on_variants` are never
populated from a definition.

This makes upstream-compatible test declarations unportable.

Related: upstream gates build-time tests by the `run_on` tag — `pre_install` runs before
`rez build -i` and aborts the install on failure, `pre_release` gates release
(`src/rezplugins/build_process/local.py:373-382`, `:427-436`; vocabulary
`docs/source/package_definition.rst:844-848`). rez-next's build step runs whatever tests it
found, unconditionally and sorted by name
(`crates/rez-next-build/src/process.rs:556-624`, `:599-600`), with no `run_on` filtering.
A package that declares `run_on: ["explicit"]` to keep an expensive test out of the build
will have that test run anyway.
```

**9. `binary_archive` download has no timeout, size cap, or scheme restriction**

```
`resolve_artifact` calls `reqwest::get(url)` with no timeout, no maximum response size,
no redirect policy and no scheme check, then buffers the whole body into memory
(`crates/rez-next-build/src/systems/binary_archive.rs:149-191`, write at `:183`).

`http://` URLs are accepted. A hanging or oversized response stalls the build
indefinitely rather than failing. Please add a timeout, a size cap, and an option to
require HTTPS.
```

**10. `Package.timestamp` exists but is never set by build or release**

```
`Package.timestamp: Option<i64>` (`crates/rez-next-package/src/package/types.rs:57-58`)
is consumed by the timestamp filter rules but assigned nowhere in the build or release
path — the only writers are `rez bind` and the Python setter.

Upstream Rez defaults it to now but honours a supplied value
(`src/rezplugins/package_repository/filesystem.py:1433-1435`).

Please set it on install (from the source definition's `timestamp`, or from
`SOURCE_DATE_EPOCH` if present) so downstream reproducibility work has a hook to use.
```

### Rez-specification-level — do **not** file as rez-next issues

These are gaps in the Rez protocol itself. They are named here for product adjudication,
not for an implementation tracker, because fixing them in rez-next would make VX packages
non-portable to upstream Rez.

1. **No integrity model in the packaging protocol.** A Rez package definition cannot state
   the digest of the bytes it will contain; there is no checksum step anywhere in the build
   pipeline. Every Rez consumer that needs supply-chain integrity invents its own
   mechanism. *(This is the root of most of VX's `build.py` strategy.)*
2. **No reproducibility model.** Rez has no `SOURCE_DATE_EPOCH`, no mtime/uid/gid/mode
   normalisation, no canonical archive format, and no sorted traversal. A Rez repository is
   a directory, so it has no byte-identity to reproduce. `timestamp` is metadata, not a
   reproducibility primitive.
3. **No per-file manifest or checksum artifact in the repository contract.** Nothing in the
   Rez repository contract enumerates the package's files with digests, or guarantees the
   file set is complete and unmodified.
4. **No declarative provenance distinct from recipe-VCS metadata.** `revision`, `changelog`,
   `release_message`, `previous_version` describe the *recipe repository*. No field carries
   an upstream third-party source URL, revision, or source digest.
5. **No declarative file-mode / executable-intent contract.** Nothing in a package
   definition states which installed files are executable; the property is inherited from
   the host filesystem and the archive, which makes Windows-authored packages lossy for
   POSIX execution permissions.
6. **No canonical architecture vocabulary.** The arch family is host-derived from
   `platform.machine()`, giving `AMD64` on Windows and `aarch64`/`arm64` on ARM while the
   same hardware is `x86_64` elsewhere. There is no defined normalisation, so
   `arch-x86_64` and `arch-AMD64` are different packages for the same machine.
7. **`rez build --install` regenerates `package.py` rather than preserving the reviewed
   definition.** Re-serialisation drops comments, formatting and all functions outside the
   five `*_commands` blocks. "The definition you installed is the definition you reviewed"
   is not a Rez guarantee.
8. **No portable build-script contract.** Upstream Rez's `custom` build system runs a shell
   command string (`build_command`); rez-next runs a Python script selected by file name.
   Neither is accepted by the other, so there is no Rez-portable way to say "run this
   script to produce my payload".
9. **`rez test` has no expected-output assertion and no timeout.** The test schema carries
   only `command`, `requires`, `run_on` and `on_variants` (`src/rez/package_resources.py:101-121`);
   success is exit status alone. Nothing in `src/rez/package_test.py` compares output or
   bounds runtime. *(Note: the build-time gate itself **is** standard — `run_on: ["pre_install"]`
   is wired at `src/rezplugins/build_process/local.py:373-382`. The gap is what a test can
   assert, not whether tests run.)*
10. **No build-time download primitive or source cache.** Rez assumes the source is local
   (`REZ_BUILD_SOURCE_PATH` is the directory containing `package.py`,
   `src/rez/build_system.py:274-278`); `rez build` accepts no URL. Every package that
   vendors a prebuilt upstream asset reimplements fetching and caching privately.
11. **No "repository as a distributable artifact" concept.** Rez transports packages as
    directories (`rez-copy`, `package_cache`). A digest-pinned, directly extractable
    repository archive has no upstream counterpart — and neither does the offline
    re-verification contract VX builds on top of it (`tools/cache_bundle.py:164-200`).

---

## Unverified / out of scope

- **`rez_next.build_plugins` helper surface** (`BuildContext`, `BuildPlugin`,
  `ExtractionBuilder`, `verify_sha256`, `extract_archive`, `copy_tree_contents`) is
  described in VX's own `docs/build-py-contract.md` and `docs/spike-rez-build-feasibility.md`
  (pinned at `vx-org/vx-rez-packages@797d12a4`, PR #13, not merged into this checkout). I
  did not read the module source, so the exact signatures are **UNVERIFIED (module not
  present in this checkout)**. The audit's conclusions do not depend on them: every claim
  about what `binary_archive` can do is cited to `rez-next/crates/rez-next-build/src/systems/binary_archive.rs`
  in this checkout.
- **Nothing here is observed behaviour.** Every upstream claim is read from source at
  `f622b81`; no `rez` or `rez-next` command was executed as part of this audit. The
  build-time test wiring in particular is read from `src/rezplugins/build_process/local.py:373-382`
  (`pre_install`), `:427-436` (`pre_release`) and `_run_tests` `:449-508`, not from a run.
- **Whether upstream Rez would accept a `build_system` plugin registered under an arbitrary
  name** is in principle possible via `rezplugins` extension paths, which would make
  `build_system = "build.py"` portable. Not investigated; **UNVERIFIED**.
- The upstream clone was scratch, held outside the repository during the audit and deleted
  afterwards. No file in this worktree was modified except this report.
