# Audit 03 — Package Repository / Distribution + Wider Ecosystem Surface

**Target:** `rez-next` (Rust reimplementation of Rez), repo `vx-org/rez-next`
**Reference spec:** upstream Rez, `nerdvegas/rez` (ASWF), branch `main`

| Item | Value |
|---|---|
| rez-next checkout | `vx-org/rez-next`, read-only working copy |
| rez-next HEAD | `97eef03928012d540f45d25fa82553da123e8786` (`97eef03`, 2026-10-11) |
| rez-next version | `0.3.10` (`.release-please-manifest.json`) |
| Upstream Rez reference | `nerdvegas/rez` @ `f622b817ef63` (2026-10-05), branch `main` |
| Method | read-only source audit; upstream files downloaded to a scratch dir and read directly. No file in either repo was modified. |

**Verdict legend**

- `ALIGNED` — behaviour and surface match the upstream Rez contract.
- `GAP (needs rez-next work)` — upstream capability is missing, wrong, or unreachable.
- `INTENTIONAL DEVIATION` — rez-next deliberately differs; documented as design choice, not a defect.

**VX impact legend** — VX = `vx-org/vx-rez-packages`, which builds multi-platform prebuilt-binary Rez
packages and publishes them as a tarball-shaped Rez repository. Its four stated needs are:
(1) filesystem package repository, (2) variant install, (3) package copy/publish, (4) deterministic payloads.

---

## 0. Corrections to the audit brief (verified against upstream)

Three paths in the brief do not exist upstream. Recording them so downstream tickets cite real locations:

| Brief said | Actual upstream location | Evidence |
|---|---|---|
| `rezplugins/package_repository/{filesystem,memory,s3}.py` | `src/rezplugins/package_repository/{filesystem,memory,rezconfig}.py` — **no `s3.py` in core Rez** | `gh api repos/nerdvegas/rez/contents/src/rezplugins/package_repository` → `__init__.py filesystem.py memory.py rezconfig.py` |
| `rezplugins/package_filter/` | `src/rez/package_filter.py` (single module, not a plugin package) | `gh api .../contents/src/rezplugins` → `build_process build_system command package_repository release_hook release_vcs shell` |
| `rezplugins/package_order/` | `src/rez/package_order.py` (single module, not a plugin package) | same listing |
| `rezplugins/bind/` | `src/rez/bind/` (binders are not `rezplugins`) | `gh api .../contents/src/rez/bind` → 16 files |

Upstream Rez plugin types are registered in `src/rez/plugin_managers.py` and are exactly:
`shell`, `release_vcs`, `release_hook`, `package_repository`, `build_system`, `build_process`, `command`
(`src/rez/plugin_managers.py:416-441`, typed `get_plugin_class` overloads; plus `register_plugin_type` at `:396`).

---

# PART A — Repository & distribution

## A1. `package_repository` plugin family

### A1.1 What rez-next actually implements

**Finding: rez-next contains TWO independent filesystem repository implementations, and only the
less faithful one is used by the Rust binary.**

**(a) `SimpleRepository` — the one everything in Rust uses.**

Evidence `crates/rez-next-repository/src/simple_repository.rs:12-33`:

```rust
/// Simplified package repository trait for solver
#[async_trait]
pub trait PackageRepository {
    async fn find_packages(&self, name: &str) -> Result<Vec<Arc<Package>>, RezCoreError>;
    async fn get_package(&self, name: &str, version: Option<&str>) -> Result<Option<Arc<Package>>, RezCoreError>;
    async fn list_packages(&self) -> Result<Vec<String>, RezCoreError>;
    fn name(&self) -> &str;
    fn root_path(&self) -> &Path;
}
```

Five methods. It has no `install_variant`, no `iter_variants`, no `iter_package_families`, no
`remove_*`, no `get_package_payload_path`, no resource handles.

Consumers: `src/cli/commands/{cp,mv,rm,env,search_v2,depends,status,diff,solve,bundle}.rs`,
`crates/rez-next-runtime/src/repository.rs`, `crates/rez-next-python/src/*`.

**(b) `FilesystemPackageRepository` — the upstream-faithful one, exposed only to Python.**

Evidence `crates/rez-next-repository/src/package_repository/mod.rs:65-264` defines the full
`PackageRepository` trait with 14 required methods mirroring upstream
(`get_package_family`, `iter_package_families`, `iter_packages`, `iter_variants`, `ignore_package`,
`unignore_package`, `remove_package`, `remove_package_family`, `remove_ignored_since`,
`install_variant`, `get_parent_package_family`, `get_parent_package`, `get_package_payload_path`, `name`)
plus 8 provided methods (`uid`, `is_empty`, `get_package`, `get_equivalent_variant`,
`make_resource_handle`, `get_variant_state_handle`, `get_last_release_time`,
`pre_variant_install`, `on_variant_install_cancelled`).

Its only Rust consumer is the PyO3 binding:

```
crates/rez-next-python/src/package_repository_bindings.rs:12
    FilesystemPackageRepository as RustFilesystemPackageRepository, PackageRepository,
crates/rez-next-python/src/package_repository_bindings.rs:153
    m.add_class::<PyFilesystemPackageRepository>()?;
```

A repo-wide grep for `package_repository::PackageRepository` in Rust (excluding the defining
module) returns **zero** hits — no CLI command, no solver, no build path uses it.

### A1.2 Which repository types exist

| Type | rez-next evidence | Status |
|---|---|---|
| filesystem | `crates/rez-next-repository/src/package_repository/filesystem.rs:18` `pub const FILESYSTEM_REPO_TYPE: &str = "filesystem";` | **IMPLEMENTED** (2 impls, see A1.1) |
| memory | `crates/rez-next-repository/src/repository.rs:35` `/// Memory-based repository (for testing)` under `pub enum RepositoryType { FileSystem, Memory, Remote }` | **ENUM VARIANT ONLY — no implementation.** No `MemoryPackageRepository` struct exists anywhere. |
| s3 / remote | `crates/rez-next-repository/src/repository.rs:37` `/// Remote repository (future)` | **ENUM VARIANT ONLY** |

Grep for `"s3"`, `S3Repository`, `s3_repository` across all `*.rs` → **0 hits**.

### A1.3 How a repository is configured and selected

rez-next reads `packages_path` as a plain `Vec<String>` of filesystem paths
(`crates/rez-next-common/src/config.rs:30`) and never inspects its entries for a type prefix:

```
$ grep -rn "split_once('@')" --include=*.rs .   →  0 matches
$ grep -rn "split('@'"       --include=*.rs .   →  0 matches
```

Each path is wrapped blindly: `src/cli/commands/cp.rs:105-109`

```rust
for (i, path) in source_paths.iter().enumerate() {
    let repo_name = format!("repo_{}", i);
    let simple_repo = SimpleRepository::new(path.clone(), repo_name);
    repo_manager.add_repository(Box::new(simple_repo));
}
```

**rez spec side.** Upstream `PackageRepositoryManager.get_repository()` accepts `type@location`
and defaults to `filesystem`; `src/rez/package_repository.py:549-586`:

```python
def get_repository(self, path: str) -> PackageRepository:
    # normalise repo path
    parts = path.split("@", 1)
    if len(parts) == 1:
        parts = ("filesystem", parts[0])
    repo_type, location = parts
    if repo_type == "filesystem":
        location = os.path.abspath(location)
    normalised_path = "%s@%s" % (repo_type, location)
```

Upstream `memory` repository exists at `src/rezplugins/package_repository/memory.py` (211 lines)
with `MemoryPackageRepository`, created by `create_memory_package_repository()`
(`src/rez/package_repository.py:31`). Upstream also caches repository instances per normalised path
(`:581-586`) and documents `are_same()` (`:588`) for path-identity comparison. rez-next has neither.

### 判定

| Aspect | 判定 |
|---|---|
| Filesystem repository (read: list/find/get) | `ALIGNED` (behaviourally sufficient) |
| `PackageRepository` plugin contract | `GAP (needs rez-next work)` — trait exists but the only implementation is unreachable from every Rust consumer; the CLI/solver path uses a 5-method shim trait with no install/remove/variant surface |
| memory repository | `GAP (needs rez-next work)` — enum variant only, no implementation |
| s3 repository | `INTENTIONAL DEVIATION` — **not present in upstream core Rez either**; no work needed for spec parity |
| `type@location` selection | `GAP (needs rez-next work)` — no `@` parsing; upstream `packages_path` entries that use it are silently treated as literal directories |
| Repository instance caching / `are_same()` | `GAP (needs rez-next work)` |

### VX impact

- Filesystem package repository: **NON-BLOCKING** — `SimpleRepository` scans `<root>/<family>/<version>/package.py`
  (`crates/rez-next-repository/src/simple_repository.rs:92-104`) and resolves correctly.
- **One caveat with real VX blast radius:** the scanner recognises **only `package.py`**
  (`crates/rez-next-repository/src/scanner_types.rs:12`):
  ```rust
  pub const REZ_PACKAGE_FILENAMES: &[&str] = &["package.py"];
  ```
  Upstream `rez/serialise.py:39-46` defines `FileFormat` as `py`, `yaml`, `txt`, and rez-next's own
  build path *does* look for yaml (`crates/rez-next-package/src/developer_package.rs:111`
  `let candidates = [dir.join("package.py"), dir.join("package.yaml")];`). If vx-rez-packages ships
  any `package.yaml`, the runtime repository will not see it while `rez build` will — a silent
  asymmetry. **Verify the format vx-rez-packages emits; if yaml, this is BLOCKING.**
  (The `vx-rez-packages` working copy in this worktree is empty, so the format could not be confirmed
  from source — `upstream-side: UNVERIFIED (vx-rez-packages checkout has no package files)`.)

---

## A2. Package repository URI scheme

### A2.1 rez-next

The only URI-aware code is `crates/rez-next-python/src/package_uri_functions.rs`. Its docstring
states the accepted forms (`package_uri_functions.rs:16-19`):

```rust
/// The URI is typically a path to a package file:
/// - `/{pkg-repo-path}/{pkg-name}/{pkg-version}/package.py`
/// - `/{pkg-repo-path}/{pkg-name}/package.py` (unversioned)
/// - `/{pkg-repo-path}/{pkg-name}/package.py<{version}>` (combined-type)
```

Resolution is a cascade of four path-shape heuristics (`:35`, `:46`, `:74`, `:79`). The accepted
input is a **filesystem path only** — there is no scheme parser anywhere:

```
$ grep -rn "://" --include=*.rs crates/rez-next-repository/src              → 0 matches
$ grep -rn "://" --include=*.rs src/cli/commands/cp.rs mv.rs rm.rs          → 0 matches
```

Variant URI lookup is explicitly unimplemented (`package_uri_functions.rs:179-207`):

```rust
pub fn get_variant_from_uri(...) -> PyResult<Option<Py<PyAny>>> {
    let _ = (uri, paths);
    Err(pyo3::exceptions::PyNotImplementedError::new_err(
        "variant URI lookup is not implemented; iterate variants from a resolved package instead",
    ))
}
```

`get_variant(uri, index, paths)` at `:197-207` raises the same error.

### A2.2 rez spec side

Upstream `src/rez/packages.py:789-852` documents the canonical forms, and critically includes the
**variant-index suffix**, which rez-next does not parse:

```
789: # assume form /{pkg-repo-path}/{pkg-name}/{pkg-version}/package.py
843: # assume form /{pkg-repo-path}/{pkg-name}/{pkg-version}/package.py[{index}]
851: # /{pkg-repo-path}/{pkg-name}/package.py[{index}] OR
852: # /{pkg-repo-path}/{pkg-name}/package.py<{version}>[{index}]
```

Upstream declares `get_package_from_uri` / `get_variant_from_uri` as abstract repository methods
(`src/rez/package_repository.py:206`, `:218`), so each repository type defines its own scheme —
this is the extension point that `type@location` (A1.3) selects.

### 判定

| Aspect | 判定 |
|---|---|
| Filesystem path URIs (`package.py`, unversioned, `<version>`) | `ALIGNED` |
| `package.py[index]` variant URI | `GAP (needs rez-next work)` — not parsed; `get_variant_from_uri` raises `NotImplementedError` |
| `s3://` / `http://` / any non-filesystem scheme | `INTENTIONAL DEVIATION` — no repository plugin of that kind exists on either side of the comparison (upstream core Rez has no s3 plugin either) |
| `type@location` in `packages_path` | `GAP (needs rez-next work)` — see A1.3 |

### VX impact

**NON-BLOCKING.** VX publishes a tarball-shaped repository consumed by filesystem path; `rez cp`
and resolution both take plain paths. The `[index]` gap matters only if VX tooling round-trips
variant URIs through `rez.packages.get_variant_from_uri`.

---

## A3. `package_filter` family

### A3.1 rez-next

Crate `crates/rez-next-package-filter/` (3 files).

Rules (`crates/rez-next-package-filter/src/rule.rs`):

| Rule | Evidence |
|---|---|
| `GlobRule` | `rule.rs:75`, ctor `:97`, `parse_rule` `:113`, `impl Rule` `:168` |
| `RegexRule` | `rule.rs:229`, ctor `:251`, `parse_rule` `:266`, `impl Rule` `:294` |
| `RangeRule` | `rule.rs:352`, ctor `:361`, `parse_rule` `:377`, `impl Rule` `:402` |
| `TimestampRule` | `rule.rs:452`, ctor `:463`, `parse_rule` `:475`, `impl Rule` `:517` |
| `Rule` trait + `RuleMatch` + `parse_rule(txt)` dispatcher | `rule.rs:43`, `:33`, `:585` |

Filter (`crates/rez-next-package-filter/src/filter.rs:19-211`): `PackageFilter::new` `:45`,
`excludes` `:57`, `includes` `:84`, `add_exclusion` `:99`, `add_inclusion` `:106`,
`add_exclusion_from_str` `:113`, `add_inclusion_from_str` `:120`, `to_pod` `:129`,
`from_pod` `:156`, `sha1` `:175`, `Display` `:211`.

### A3.2 rez spec side

`src/rez/package_filter.py` (598 lines):

```
 21: class PackageFilterBase      97: class PackageFilter      234: class PackageFilterList
333: class Rule                  436: class RegexRuleBase      455: class RegexRule
473: class GlobRule              491: class RangeRule          519: class TimestampRule
```

Rule set is **identical**: Glob, Regex, Range, Timestamp. Upstream additionally has
`PackageFilterList` (`:234`), `PackageFilter.copy()` (`:148`), `__and__` composition (`:158`),
`cost()` heuristics (`:171`, `Rule.cost` `:359`), and `PackageFilterBase.iter_packages()` (`:65`).

### 判定

| Aspect | 判定 |
|---|---|
| The four rule types + `PackageFilter` core | `ALIGNED` |
| `PackageFilterList`, `copy()`, `__and__`, `cost()` | `GAP (needs rez-next work)` — absent |
| Config wiring (`package_filter` setting) | `GAP (needs rez-next work)` — **`package_filter` is not a field of `RezCoreConfig`** (`crates/rez-next-common/src/config.rs:10-67`, 19 fields, none is `package_filter`). It exists only as a Python-side default (`crates/rez-next-python/python/rez_next/config.py:566`, schema `:1049`), which the Rust binary never reads. So a studio `package_filter` in `rezconfig` has no effect on `rez env` / `rez search`. |

### VX impact

**NON-BLOCKING.** VX does not depend on package filtering. Filter rules are library-correct; only
the config plumbing is missing.

---

## A4. `package_order` family

### A4.1 rez-next

Lives in the package crate, not a filter crate: `crates/rez-next-package/src/package_order.rs` (669 lines).

| Orderer | Evidence |
|---|---|
| `PackageOrder` trait | `:15` |
| `NullPackageOrder` | `:59`, `impl` `:69` |
| `SortedOrder` | `:97`, ctor `:103`, `impl` `:111` |
| `VersionSplitPackageOrder` | `:164`, ctor `:170`, `impl` `:178` |
| `PerFamilyOrder` | `:226`, ctor `:232`, `impl` `:243` |
| `TimestampPackageOrder` | `:310`, ctor `:317`, `impl` `:326` |
| `PackageOrderList` | `:374`, `from_pod` `:385`, `to_pod` `:395`, `get` `:399`, `append` `:413` |
| `to_pod` / `from_pod` / `get_orderer` free fns | `:425`, `:430`, `:485` |

### A4.2 rez spec side

`src/rez/package_order.py` (771 lines):

```
 53: class PackageOrder      205: NullPackageOrder      243: SortedOrder
297: PerFamilyOrder          415: VersionSplitPackageOrder
468: TimestampPackageOrder   635: PackageOrderList
```

**One-to-one match on all five orderers plus the list type.**

### 判定

| Aspect | 判定 |
|---|---|
| Orderer type set | `ALIGNED` — exactly the five upstream orderers |
| Config wiring (`package_orderers`) | `GAP (needs rez-next work)` — absent from `RezCoreConfig`; Python-side only (`config.py:569`, used at `crates/rez-next-python/python/rez_next/resolver.py:63`). Rust resolution ignores it. |

### VX impact

**NON-BLOCKING.**

---

## A5. `package_copy` / `package_move` / `package_remove` — CLI + Python surface

### A5.1 rez-next `rez cp`

`src/cli/commands/cp.rs:13-46`:

| Flag | Line | Notes |
|---|---|---|
| `SRC_PKG` (positional) | `:16-17` | required |
| `DEST_PATH` (positional) | `:20-21` | required |
| `--src-path PATH` | `:24-25` | long only, no `-p` |
| `-a, --all-variants` | `:28-29` | **cosmetic** — see below |
| `-f, --force` | `:32-33` | overwrite |
| `-n, --dry-run` | `:36-37` | real (`:149-158`) |
| `-v, --verbose` | `:40-41` | |
| `--no-deps` | `:44-45` | **dead — zero reads** |

The copy itself is a naive recursive `std::fs::copy` (`cp.rs:289-305`), and variant handling is
reporting-only (`cp.rs:273-277`):

```rust
let variants_copied = if args.all_variants {
    source_package.variants.len().max(1)
} else {
    1
};
```

`rez mv` mirrors this exactly (`src/cli/commands/mv.rs:285-301`: `copy_dir_recursive` then
`remove_dir_all`, with an extra `--keep-source` at `:48-49`), and shares the same cosmetic
`--all-variants` (`:306-310`) and dead `--no-deps` (`:44-45`).

`rez rm` (`src/cli/commands/rm.rs:13-54`) has `-f/--family` (note: `-f` is **family**, not force),
`--force-family`, `--ignored-since TIME`, `--paths`, `-a/--all-variants`, `--force` (long only),
`-n/--dry-run`, `-v/--verbose`, `-i/--interactive`. Package and family removal are real
(`rm.rs:475-481`, `:446-451`).

### A5.2 The Python surface — and a third, divergent implementation

`crates/rez-next-python/python/rez_next/package_copy.py:80-176` exposes an upstream-shaped
`copy_package()` with `variants`, `shallow`, `dest_name`, `dest_version`, `overwrite`, `force`,
`follow_symlinks`, `dry_run`, `keep_timestamp`, `skip_payload`, `overrides`, `verbose` — but
**rejects most of them** (`package_copy.py:121-135`):

```python
if shallow:
    raise PackageCopyError("Shallow copy (symlinks) not yet supported in rez-next")

unsupported = {
    "variants": variants is not None,
    "dest_name": dest_name is not None,
    "dest_version": dest_version is not None,
    "follow_symlinks": follow_symlinks,
    "dry_run": dry_run,
    "keep_timestamp": keep_timestamp,
    "skip_payload": skip_payload,
}
requested = [name for name, enabled in unsupported.items() if enabled]
if requested:
    raise PackageCopyError("Unsupported copy options: " + ", ".join(requested))
```

There is also a Rust domain implementation, `crates/rez-next-package/src/package_copy.rs:90-126`,
whose `PackageCopyConfig` (`:57-64`) has only `packages_path`, `force`, `normalize_paths`.

**The CLI does not use the domain implementation.** Grep for `package_copy` across `src/` returns
zero hits; `cp.rs` has its own `copy_dir_recursive`. So there are **three** copy code paths
(CLI, Rust domain, Python wrapper) with three different flag sets.

### A5.3 rez spec side

Upstream `rez cp` (`src/rez/cli/cp.py:11-59`) flags:

```
--dest-path PATH   --paths PATHS     --nl/--no-local
--reversion VERSION                  --rename NAME
-o/--overwrite     -s/--shallow      --follow-symlinks
-k/--keep-timestamp                  -f/--force
--allow-empty      --dry-run
--variants INDEX [INDEX ...]         --variant-uri URI
PKG                DEST
```

Upstream `rez mv` (`src/rez/cli/mv.py:11-30`): `-d/--dest-path` (required), `-k/--keep-timestamp`,
`-f/--force`, `PKG`, `PATH`.
Upstream `rez rm` (`src/rez/cli/rm.py:15-40`): `-p/--package`, `-f/--family`, `--force-family`,
`-i/--ignored-since DAYS`, `--dry-run`, `PATH`.

Semantically, upstream `copy_package()` (`src/rez/package_copy.py:31-`) works **at variant
granularity through the repository plugin**: it checks relocatability (`:117-121`),
resolves variant indices (`:138-144`), and installs each source variant via
`dest_pkg_repo.install_variant(...)` (`:169`). rez-next never calls any repository install hook.

### 判定

| Capability | 判定 |
|---|---|
| `rez cp` / `rez mv` / `rez rm` exist and do real filesystem work | `ALIGNED` (basic) |
| `--keep-timestamp` | `GAP (needs rez-next work)` — absent on both CLI and Python (`package_copy.py` raises on it) |
| `--variants INDEX…` / `--variant-uri` | `GAP (needs rez-next work)` — absent; `--all-variants` is a print counter only |
| `-s/--shallow`, `--follow-symlinks` | `GAP (needs rez-next work)` — absent; `shallow` raises `PackageCopyError` |
| `--rename` / `--reversion` (`--dest-name` / `--dest-version`) | `GAP (needs rez-next work)` — accepted by the Python signature then rejected |
| relocatable check (`-f/--force` semantics) | `GAP (needs rez-next work)` — rez-next's `-f` means "overwrite", upstream's means "copy even if not relocatable"; different semantics, easy to misuse |
| `--allow-empty` | `GAP (needs rez-next work)` — absent |
| `--paths` / `-p` | `GAP (needs rez-next work)` — rez-next uses `--src-path` (`cp`) / `--paths` (`rm`); no `-p` short form, and `rm`'s `--ignored-since` path reads `args.paths` directly (`rm.rs:301`) so it silently finds nothing without an explicit `--paths` |
| Copy routes through `PackageRepository.install_variant` | `GAP (needs rez-next work)` — see A1.4 / A6 |
| Three divergent copy implementations | `GAP (needs rez-next work)` — `src/cli/commands/cp.rs:289`, `crates/rez-next-package/src/package_copy.rs:168`, `crates/rez-next-python/python/rez_next/package_copy.py:80` |

### VX impact

**BLOCKING** for two of the four stated VX needs:

- **package copy/publish:** the copy works, but it bypasses `install_variant`, so it cannot
  rename/reversion, cannot select variants, and does not honour relocatability.
- **deterministic payloads:** no `--keep-timestamp`. Every `rez cp` rewrites mtimes to copy time,
  so two copies of the same package are not byte-identical as directory trees and any downstream
  digest over the tree (not the file contents) will differ.

---

## A6. Variant install — the single largest gap in this scope

`FilesystemPackageRepository::install_variant` is **not implemented**
(`crates/rez-next-repository/src/package_repository/filesystem.rs:538-548`):

```rust
fn install_variant(
    &mut self,
    _variant: &VariantResource,
    _dry_run: bool,
    _overrides: Option<HashMap<String, serde_json::Value>>,
) -> Result<Option<PackageResource>, RezCoreError> {
    Err(RezCoreError::Repository(
        "Filesystem variant installation is not implemented; use the build or release workflow"
            .to_string(),
    ))
}
```

The repo's own test asserts it fails closed (`filesystem.rs:967-980`):

```rust
#[test]
fn install_variant_fails_closed_until_supported() {
    ...
    assert!(repo.install_variant(&variant, false, None).is_err());
}
```

`iter_variants` is likewise a stub that always returns exactly one synthetic variant
(`filesystem.rs:315-325`):

```rust
// For now, create a single variant (index 0)
// In a full implementation, would parse package.py for variants
let variant = VariantResource::new(package.name().to_string(), Some(version_str), 0, ...);
```

**Partial mitigation that exists:** `crates/rez-next-package/src/install_layout.rs` computes the
canonical Rez variant subpath correctly, including hashed variants
(`install_layout.rs:64-87` — SHA1 of the Python list repr, matching upstream
`VariantResourceHelper._subpath`), and it *is* wired into the build/release path:

```
crates/rez-next-build/src/builder.rs:287   let layout = PackageInstallLayout::for_variant(...)?;
crates/rez-next-build/src/release.rs:525-528  per-variant layouts
crates/rez-next-build/src/release.rs:546-560  creates variant dirs + metadata
```

So `rez build` / `rez release` install variants correctly. What does **not** exist is the
repository-level `install_variant` entry point that `rez cp` / `rez.package_copy` / any
repository-to-repository publish would call.

**rez spec side.** Upstream `src/rezplugins/package_repository/filesystem.py:install_variant`
creates the repo path, applies `overrides` (including `name`/`version` reversioning, with a
`remove` sentinel), locks the package during install, and delegates to `_create_variant`
which handles payload copy, shallow symlinking and timestamp preservation. Its return type is a
`VariantResource`; rez-next's trait returns `Option<PackageResource>` — a signature deviation that
would need reconciling.

### 判定

`GAP (needs rez-next work)`

### VX impact

**BLOCKING.** VX needs variant install to publish multi-platform prebuilt binaries as a Rez
repository. Today the only route is `rez build`/`rez release` from source — there is no
"install this already-built variant payload into repository X" operation, which is exactly what a
tarball-shaped distribution pipeline needs.

---

## A7. Caching — memcached and everything else

### A7.1 memcached: absent

Verified by exhaustive grep.

```
$ grep -rni "memcach" --include=*.rs --include=*.toml --include=*.py --include=*.md .   (excluding target/)
```

Every hit is a **declaration with no consumer**:

| Evidence | What it is |
|---|---|
| `crates/rez-next-python/python/rez_next/config.py:465` | `memcached_uri: list[str] = []` — module default |
| `crates/rez-next-python/python/rez_next/config.py:468,471,474,477` | `memcached_*_min_compress_len` defaults |
| `crates/rez-next-python/python/rez_next/config.py:701-705` | `debug_resolve_memcache`, `debug_memcache` |
| `crates/rez-next-python/python/rez_next/config.py:946` | `"memcached_uri": OptionalStrList` — schema entry |
| `crates/rez-next-python/python/rez_next/rezconfig.py:38` | packaged default |
| `crates/rez-next-python/python/rez_next/serialise.py:89` | doc: "`disable_memcache`: If True, skip memcache (**no-op in this impl**)." |

`pylibmc` → 0 hits. `cached_package_repositories` → 0 hits. No memcached/Redis crate in any
`Cargo.toml`, no memcached entry in `Cargo.lock`, and `crates/rez-next-python/pyproject.toml:12`
declares `dependencies = []`.

### A7.2 What caching does exist

| Cache | Evidence | Kind |
|---|---|---|
| `rez-next-cache` `IntelligentCacheManager` | `crates/rez-next-cache/src/intelligent_manager.rs:107-110` | L1 `DashMap` in-memory; the "L2 disk" is typed `tokio::sync::RwLock<HashMap>` — **also in-memory**, contradicting its own doc comment |
| `rez-next-package-cache` `InMemoryCache` / `FileCache` | `crates/rez-next-package-cache/src/lib.rs:130`, `:216` | DashMap / JSON-per-entry on disk — **but grep for `rez_next_package_cache` across all `*.rs` returns 0 hits: dead crate** |
| `RepositoryCache` | `crates/rez-next-repository/src/cache.rs:121` | TTL + source-mtime validated (`:56-76`); **never instantiated** |
| Scanner scan cache | `crates/rez-next-repository/src/scanner/mod.rs:35` | in-memory `DashMap`, mtime+size validated (`scanner/cache.rs:196-203`) |
| Variant payload cache | `crates/rez-next-package/src/package_cache.rs:221`; CLI `src/cli/commands/pkg_cache/ops.rs:12-34` | **disk**, `~/.rez/cache/packages` — the upstream `rez/package_cache.py` analogue |
| Solver cache | `crates/rez-next-solver/src/cache.rs:118` | in-memory; **not compiled** — absent from the module list in `crates/rez-next-solver/src/lib.rs:10-23` |

### A7.3 rez spec side

Upstream `rez/utils/resources.py` provides `ResourcePool` (`:204`), `ResourceHandle` (`:152`),
`ResourceWrapper` (`:253`) and a `cached_manager` / `ResourceCache` layer; `resource_caching_maxsize`
(`src/rez/config.py:474`) sizes the pool, and `memcached_uri` (`src/rez/config.py:425`) backs
`cached_listdir` / `cached_package_files` / resolve caching. Upstream also ships a `rez-memcache`
console script (from `src/rez/cli/_entry_points.py`, script list below).

rez-next has a `ResourcePool` type (`crates/rez-next-repository/src/resources/mod.rs`, re-exported
at `crates/rez-next-repository/src/lib.rs:32-34`) and `PackageFamilyResource` / `PackageResource` /
`VariantResource` (`resources/{family,package,variant}.rs`), so the *shape* is present — but there
is no `CachedFile`/`cached_manager` equivalent and no `resources.rs`.

### 判定

| Aspect | 判定 |
|---|---|
| memcached backend | `INTENTIONAL DEVIATION` — a Rust implementation does not need memcached for package-file caching; the rewrite's premise is that the resolver is fast enough in-process. **However**: the `memcached_*` config keys are silently accepted and ignored. If a studio sets `memcached_uri` expecting upstream behaviour, it gets none and no warning. Recommend either implementing or hard-failing/surfacing a warning — tracked as a follow-up, not a parity blocker. |
| `cached_package_repositories` | `GAP (needs rez-next work)` — absent entirely |
| `resource_caching_maxsize` | `GAP (needs rez-next work)` — declared at `config.py:462`, no consumer |
| `rez/utils/resources.py` cached-loading equivalent | `GAP (needs rez-next work)` — no `CachedFile` / `cached_manager`; the closest analogue (`rez-next-package-cache::FileCache`) is unwired |
| Variant payload cache | `ALIGNED` — real, on disk, CLI-reachable |

### VX impact

**NON-BLOCKING.** VX needs deterministic payloads, not a distributed cache. The one caveat: the
dead `rez-next-package-cache` crate is the only mtime-invalidated persistent *definition* cache,
and it is unwired — so a large VX repository pays a full rescan per invocation. That is a
performance concern, not a correctness one.

---

# PART B — Wider ecosystem surface

## B1. `rez bind`

### rez-next

Two lists that disagree with each other.

**Crate-level binders** (`crates/rez-next-bind/src/builtin_binders.rs:55-127`) — 12 entries:
`python`, `cmake`, `git`, `pip`, `gcc`, `clang`, `node`, `rust`, `go`, `java`, `ffmpeg`, `imagemagick`.

**CLI detector** (`src/cli/commands/bind/detect.rs:24-36`) — 11 names:

```rust
pub fn detect_system_tool(name: &str) -> Option<DetectedTool> {
    match name {
        "python" => detect_python(), "pip" => detect_pip(), "cmake" => detect_cmake(),
        "git" => detect_git(), "gcc" => detect_gcc(), "clang" => detect_clang(),
        "setuptools" => detect_setuptools(),
        "platform" | "arch" | "os" | "rez" => detect_platform_package(name),
        _ => None,
    }
}
```

`node`, `rust`, `go`, `java`, `ffmpeg`, `imagemagick` are declared in the crate but **not
detectable** from the CLI; conversely `setuptools`, `platform`, `arch`, `os`, `rez` are detectable
but not in the crate table. On a miss the version silently degrades to `1.0.0`
(`src/cli/commands/bind/mod.rs:314-317`):

```rust
let version_str = detected.as_ref().map(|d| d.version.clone())
    .unwrap_or_else(|| "1.0.0".to_string());
```

Module listing is hardcoded — `src/cli/commands/bind/utils.rs:30-67` returns a fixed array with
synthetic `builtin://<name>` paths (`utils.rs:58`), so `-l/--list` and `-s/--search` never reflect
the filesystem. Flags: `PKG`, `--quickstart`, `-r/--release`, `-i/--install-path`, `--no-deps`,
`-l/--list`, `-s/--search`, `-v/--verbose`, trailing `bind_args` (dead).

### rez spec side

Upstream binders live in `src/rez/bind/` (not `rezplugins`) and are discovered as modules:
`PyQt.py PySide.py __init__.py _pymodule.py _utils.py arch.py cmake.py gcc.py hello_world.py
os.py pip.py platform.py python.py rez.py rezgui.py setuptools.py sip.py` — 14 binders. Upstream
`rez bind -l` enumerates `rez.bind.*` modules from disk.

### 判定

`GAP (needs rez-next work)` — hardcoded, no plugin discovery, DCC/host binders absent
(`maya`, `nuke`, `houdini`, `pymel`, `sip`, `PySide`, `PyQt`, `hello_world`, `rezgui` all absent),
and the two binder tables disagree.

### VX impact

**NON-BLOCKING.** VX consumes prebuilt binaries; it does not rely on `rez bind` for DCC hosts.

---

## B2. `rez pip`

### rez-next

**CLI is real.** `src/cli/commands/pip.rs:14-50` flags: `PKG_SPEC…`, `--release`, `--prefix PATH`,
`--python PYTHON`, `-r/--requirement FILE`, `--no-deps`, `--force`, `--dry-run`, `-v/--verbose`.
It genuinely shells out (`pip.rs:177-181`):

```rust
let mut cmd = Command::new(python);
cmd.args(["-m", "pip", "install", "--target", &target_str, spec]);
if args.no_deps { cmd.arg("--no-deps"); }
```

then reads metadata from `pip show --files` (`:218-221`) and writes a generated `package.py`
(`create_rez_package`, `:318`). No variant support; no index-url passthrough; `requires` are
derived by naive lowercasing (`:331-336`).

**Python module is a stub.** `crates/rez-next-python/python/rez_next/pip.py` is 2 lines:

```python
import rez_next._native  # ensure extension module is initialized  # noqa: F401
from rez_next._native.pip import *  # noqa: F401,F403
```

and the binding it forwards to discards its arguments
(`crates/rez-next-python/src/pip_bindings.rs:158`):

```rust
let _ = (python_version, install_path, release);
```

No process spawn, no network, no disk write.

### rez spec side

Upstream `src/rez/cli/pip.py:15-37` flags: `--python-version`, `-i/--install`, `-r/--release`,
`-p/--prefix`, `PACKAGE`, `-e/--extra` (REMAINDER passthrough). `src/rez/pip.py` (636 lines)
implements `pip_install_package()` with full dist-info parsing, variant-aware dependency
generation, and `rez` package emission.

### 判定

`GAP (needs rez-next work)` — CLI is a functional shell-out wrapper but is not the upstream
integration (no `--extra` passthrough, no `pip_install_package` API, no variant support); the
Python surface is a stub.

### VX impact

**NON-BLOCKING.** VX ships prebuilt binaries, not pip-installed Python packages.

---

## B3. `rez env` / `rez context`

### rez-next

**`rez env` is the most complete command in the tree.** `src/cli/commands/env.rs:271-277` performs
a real solve:

```rust
let solver_config = SolverConfig { max_time_seconds: args.max_solve_time.unwrap_or(300), strict_mode: true, ..SolverConfig::default() };
let mut resolver = DependencyResolver::new(Arc::clone(&repo_arc), solver_config);
let resolution = rt.block_on(resolver.resolve(resolver_reqs))?;
```

Real context persistence (`:173-178`, exported as `REZ_RXT_FILE` at `:378-383`) and real shell
spawn (`:654-715`).

**However, 10 declared flags are dead** (grep-verified, zero reads of `args.<field>`):
`--rcfile`, `--norc`, `--stdin`, `--new-session`, `--detached`, `--pre-command`, `--time`,
`-v/--verbose`, `--fail-fast`, `--fail-graph`.

**`rez env --output` / `-o` does not exist** — no such flag on `EnvArgs` (`env.rs:21-117`).
Upstream `rez env -o FILE` writes the context to a file.

**`rez context` is PARTIAL.** `src/cli/commands/context.rs:14-85` has 18 flags; 5 are dead
(`-d/--dependency-graph`, `--no-env`, `--diff`, `--fetch`, `-s/--style`). `--interpret` filters by
literal string match (`context.rs:375-377`):

```rust
if let Some(ref commands) = resolved_pkg.package.commands
    && commands.contains(&format!("export {}", var_name))
```

so any package using `env.PATH.prepend(...)` or a `commands()` function — the normal Rez style —
is filtered out of `--interpret` output.

### rez spec side

Upstream `src/rez/cli/env.py` (279 lines) and `src/rez/cli/context.py` (197 lines).

### 判定

| Aspect | 判定 |
|---|---|
| `rez env` solve → environment → shell spawn | `ALIGNED` |
| `rez env -o/--output` | `GAP (needs rez-next work)` — absent |
| `rez env --rcfile/--norc/--new-session/--detached/--pre-command/--time/--fail-graph` | `GAP (needs rez-next work)` — declared, never read |
| `rez context` load/print/graph | `ALIGNED` |
| `rez context --diff` / `--fetch` / `--no-env` / `-d` / `-s` | `GAP (needs rez-next work)` — dead flags |
| `rez context --interpret` | `GAP (needs rez-next work)` — string-match heuristic, not real resolution |

### VX impact

**NON-BLOCKING** (core env/resolve works). `--interpret` accuracy matters if VX debugs resolved
environments; note it as a quality issue.

---

## B4. Suite tooling

### rez-next

`rez suites` is **real** and delegates to the `rez-next-suites` crate. Eight subcommands
(`src/cli/commands/suites.rs:24-53`): `create`, `list`, `info`, `add-context`, `remove-context`,
`alias-tool`, `hide-tool`, `tools`, plus `--paths`.

Crate API (`crates/rez-next-suites/src/suite.rs`): `Suite::new` `:58`, `with_description` `:69`,
`with_conflict_mode` `:75`, `add_context` `:85`, `remove_context` `:110`, `alias_tool` `:141`,
`hide_tool` `:155`, `get_tools` `:166`, `save` `:237`, `load` `:266`, `is_suite` `:297`,
`print_info` `:347`. Supporting types: `suite_context.rs`, `suite_tool.rs`, `suite_manager.rs`.

### rez spec side

Upstream `src/rez/suite.py` provides the `Suite` class with `add_context`, `remove_context`,
`alias_tool`, `hide_tool`, `get_tools`, `save`, `load`, `validate`, `context_names`, plus suite
caching and `Suite` visibility. Upstream `rez suite` also supports `--reload` / `--drop`.

### 判定

`ALIGNED` (core suite model). Minor gaps: `--reload` / `--drop` absent; suite caching absent.

### VX impact

**NON-BLOCKING.**

---

## B5. Shell plugin family

### rez-next

Five shells are really implemented. `crates/rez-next-rex/src/shell.rs:41-46` dispatches:

```rust
ShellType::Bash | ShellType::Zsh => generate_bash_script(env),
ShellType::Fish => generate_fish_script(env),
ShellType::Cmd  => generate_cmd_script(env),
ShellType::PowerShell => generate_powershell_script(env),
```

with emitters at `shell.rs:61` (`export K="V"`), `:118` (`set -gx K "V"`), `:160`
(`SET "K=V"`), `:205-209` (`$env:K = 'V'`).

The authoritative capability surface (`crates/rez-next-python/src/shell_bindings.rs:104-106`):

```rust
pub fn get_available_shells() -> Vec<&'static str> {
    vec!["bash", "zsh", "fish", "cmd", "powershell"]
}
```

`pwsh` is only a parse alias (`crates/rez-next-rex/src/shell.rs:26`:
`"powershell" | "pwsh" => Ok(Self::PowerShell)`). `sh` is accepted at exactly one of four dispatch
sites (`src/cli/commands/env.rs:468` `"bash" | "sh" => RexShellType::Bash`).

`csh` and `tcsh` appear **only** as inert description records
(`crates/rez-next-python/src/plugins_bindings.rs:174-175`) and the repo's own test asserts `tcsh`
fails (`crates/rez-next-python/src/shell_bindings_tests.rs:207-208`). `gitbash` → 0 repo-wide hits.

**No trait, no registry** — two duplicated `ShellType` enums
(`crates/rez-next-context/src/shell.rs:11-23` and `crates/rez-next-rex/src/shell.rs:8-15`) and
~14 hardcoded match sites, including three divergent emitters
(`rex/src/shell.rs`, `context/src/environment.rs:410-466`, `build/src/environment.rs:383-408`)
that disagree on quoting and on fish syntax (`set -gx` vs `set -x`).

`default_shell` is a **dead config key**: defined at `crates/rez-next-common/src/config.rs:39`,
printed by `rez config` (`src/cli/commands/config.rs:152`) and `rez -i` (`src/cli/mod.rs:229`),
but never read by `src/cli/commands/env.rs`.

### rez spec side

Upstream `src/rezplugins/shell/` contains: `bash.py cmd.py csh.py gitbash.py powershell.py pwsh.py
sh.py tcsh.py zsh.py` (+ `_utils`, `__init__`, `rezconfig`) — **9 shells**, each a real plugin
class registered through `rez.plugin_managers`.

### 判定

| Shell | 判定 |
|---|---|
| bash, zsh, fish, cmd, powershell | `ALIGNED` |
| sh | `GAP (needs rez-next work)` — accepted at 1 of 4 dispatch sites; no distinct emitter |
| csh, tcsh | `GAP (needs rez-next work)` — absent (metadata-only entries that mislead `rez plugins`) |
| gitbash | `GAP (needs rez-next work)` — absent |
| pwsh | `GAP (needs rez-next work)` — parse alias only, not a distinct plugin |
| Shell plugin architecture (trait + registry) | `GAP (needs rez-next work)` — hardcoded match over two duplicated enums; three divergent emitters |
| `default_shell` wiring | `GAP (needs rez-next work)` — key exists but is never consumed |

### VX impact

**NON-BLOCKING** for a Linux/macOS/Windows CI publishing pipeline — bash, cmd and powershell
cover it. It becomes relevant if VX consumers run `rez env` under tcsh/csh (common in VFX
facilities).

---

## B6. `yaml2py`

### rez-next

**ABSENT.** Repo-wide grep for `yaml2py` across all file types → **0 hits**.

- No `rez-yaml2py` console script (no `[project.scripts]` anywhere — see B11).
- No `rez_next.utils` package at all (upstream's `rez/utils/yaml.py`).
- No `yaml2py.py` under `crates/rez-next-python/python/rez_next/`.

### rez spec side

Upstream `src/rez/cli/yaml2py.py` (40 lines): `PATH` positional (file or directory; cwd if
omitted), loads via `get_developer_package(path, format=FileFormat.yaml)` and calls
`package.print_info(format_=FileFormat.py)`. Shipped as the `rez-yaml2py` console script.

### 判定

`GAP (needs rez-next work)`

### VX impact

**NON-BLOCKING** on its own, but note the interaction with A1: rez-next's *build* path reads
`package.yaml` (`crates/rez-next-package/src/developer_package.rs:111`) while its *repository
scanner* recognises only `package.py` (`scanner_types.rs:12`). If VX authors in yaml and converts
for distribution, the missing `yaml2py` forces a manual conversion step.

---

## B7. `rez plugins` and the plugin meta/type registry

### rez-next

**The CLI command is a stub.** `src/cli/commands/plugins.rs:59-66`:

```rust
if args.package.is_none() {
    println!("Available plugin types: build_process, build_system, release_hook, release_vcs, shell");
    println!("Built-in build_system plugins: binary_archive, pypi");
    println!("Use 'rez plugins <package>' to list plugins for a specific package.");
    return Ok(());
}
```

With a package, `discover_plugins` (`:144`) runs four substring heuristics over already-parsed
fields: `discover_command_plugins` (`:174`, one plugin per `package.tools` entry),
`discover_build_plugins` (`:193`, 10 hardcoded substrings — note `cmake` contains `make`, so a
cmake package reports both `cmake_build` and `make_build`, asserted as expected at `:362-367`),
`discover_shell_plugins` (`:229`, 5 hardcoded names), and `discover_extension_plugins` (`:252`,
true if `package.name.contains("plugin")`).

Nothing loads `rezplugins`, reads entry points, or inspects the filesystem.

**The registry is a hardcoded literal table.** `crates/rez-next-python/src/plugins_bindings.rs:164-229`
pushes fixed string tuples — 9 shells, 7 build systems, 2 release hooks, 1 package_repository.
`get_plugin_manager()` (`:235`) returns a **new** manager per call despite the "singleton"
docstring at `:232`.

**The Python port is faithful but both discovery paths are dead.**
`crates/rez-next-python/python/rez_next/plugin_managers.py:110` imports `rezplugins.<type>` —
`rezplugins` does not exist anywhere in rez-next; `:139` reads entry-point group `rez.plugins.<type>`
— no entry points are declared anywhere. So `get_plugins()` always returns `[]`. `plugin_path`
*is* read (`:57`, inside `extend_path()`), but `extend_path()` has zero call sites repo-wide.

### rez spec side

Upstream `src/rez/cli/plugins.py:11-22` is `--paths` + `PKG`, and `command()` calls
`rez.package_search.get_plugins(package_name=..., paths=...)` — a real scan for packages whose
`plugin_for` matches. Upstream `src/rez/plugin_managers.py` implements `RezPluginType` (`:103`),
`RezPluginManager` (`:300`), `register_plugin_type` (`:396`), `get_plugin_types` (`:404`),
`get_plugins` (`:410`), `get_plugin_class` (`:416-448`), `get_plugin_module` (`:448`),
`get_failed_plugins` (`:463`), `create_instance` (`:473`), backed by namespace-package discovery
over `rezplugins/<type>/`.

**Partial rez-next parity that does exist:** `crates/rez-next-repository/src/package_search.rs:65`
implements `get_plugins(package_name, paths)` by scanning for `plugin_for == package_name` — a real
implementation, but `rez plugins` does not call it.

### 判定

`GAP (needs rez-next work)` — no plugin discovery mechanism, no loading of third-party plugins,
`rez plugins` output is fabricated, and the one faithful Python port has both discovery paths dead.

### VX impact

**NON-BLOCKING**, but it means VX cannot ship a custom `package_repository` or `release_hook`
plugin for rez-next; any extensibility must be upstreamed into the binary.

---

## B8. `rez-depends` / `rez-search`

### rez-next

**No console scripts exist.** Only two binaries ship (`Cargo.toml:84-90`: `rez-next`, `rez`);
`crates/rez-next-python/pyproject.toml` has no `[project.scripts]`. `depends` and `search` exist
only as clap subcommands of `rez`.

**`rez search` is real.** `src/cli/commands/search_v2/types.rs:10-74` (16 flags: `-r/--repository`,
`--description`, `-t/--tools`, `--requirements`, `--case-sensitive`, `--regex`, `--latest-only`,
`--limit N` (default 50), `-f/--format`, `--sort`, `-v/--verbose`, `--newer-than`, `--older-than`,
`--type`, `--has-variant`). `filter::perform_search` (`filter.rs:14`) correctly uses
`repo_manager.list_packages()` (`:25`) — the one command that enumerates correctly. Real scoring
(`matcher.rs:20-167`), sorting (`filter.rs:124`), `--latest-only` (`:154`) and three formatters
(`display.rs:41`, `:97`, `:122`).

Deviation: `QUERY` is a **required** positional (`types.rs:13-14`), whereas upstream `rez search`
with no query lists everything.

**`rez depends` is broken in practice.** `src/cli/commands/depends.rs:263-264`:

```rust
// Get all packages by searching with empty string (gets all)
let all_packages = repo_manager.find_packages("").await?;
```

`find_packages` is an exact cache-key lookup — `crates/rez-next-repository/src/simple_repository.rs:162-163`:

```rust
let cache = self.package_cache.read().await;
Ok(cache.get(name).cloned().unwrap_or_default())
```

`""` is never a key, so this always returns `[]`. The repo's own binding documents the trap
(`crates/rez-next-python/src/depends_bindings.rs:181-182`):

```
// Collect all packages: list_packages() returns package names, then fetch each by name.
// find_packages("") never matches anything because "" is not a valid package name.
```

The Python binding was refactored to `list_packages()` + per-name lookup; `depends.rs` was not.
Net effect: `rez depends` always prints "No packages depend on X" and exits 0. The same bug
affects `rez status --families` (`status.rs:254`) and bare `rez status` (`status.rs:321`).

### rez spec side

Upstream scripts `rez-depends` and `rez-search` are real console scripts (see B11 list), backed by
`src/rez/cli/depends.py` (86 lines) and `src/rez/cli/search.py` (122 lines), both of which
enumerate via `rez.package_search`.

### 判定

| Aspect | 判定 |
|---|---|
| `rez search` functionality | `ALIGNED` (minus the required-QUERY deviation) |
| `rez-depends` / `rez-search` console scripts | `GAP (needs rez-next work)` — absent; only clap subcommands |
| `rez depends` correctness | `GAP (needs rez-next work)` — always returns empty due to `find_packages("")` |
| `rez status` family/overview counts | `GAP (needs rez-next work)` — same root cause |

### VX impact

**NON-BLOCKING** for publishing, but "reverse dependency lookup" is a standard VX release-gate
query and it silently returns a wrong (empty) answer rather than an error — that is a correctness
trap, not just a missing feature.

---

## B9. `rez config` — config system parity

### rez-next

**Three disjoint config systems; the binary uses the smallest one.**

| System | Evidence | Used by |
|---|---|---|
| `RezCoreConfig` — **19 fields** | `crates/rez-next-common/src/config.rs:10-67` | the `rez` / `rez-next` binary |
| `rez-next-config::Config` — generic JSON value tree | `crates/rez-next-config/src/lib.rs:75-82` | PyO3 only (`crates/rez-next-python/src/config_bindings.rs:9`); grep for `rez_next_config` across `crates/` and `src/` returns only that file |
| `rez_next.config.Config` — **141 schema keys** | `crates/rez-next-python/python/rez_next/config.py:917-1058` | Python only; never read by the binary |

The 19 binary-visible fields: `use_rust_version`, `use_rust_solver`, `use_rust_repository`,
`rust_fallback`, `thread_count`, `cache`, `packages_path`, `local_packages_path`,
`release_packages_path`, `default_shell`, `version`, `plugin_path`, `package_cache_path`, `tmpdir`,
`editor`, `image_viewer`, `browser`, `difftool`, `terminal_emulator_command`.

**Loading** (`crates/rez-next-common/src/config.rs:204-237`) tries YAML then JSON, and **breaks on
the first parseable file** — no layering/merge:

```rust
for path in Self::get_search_paths() {
    if path.exists() && let Ok(content) = std::fs::read_to_string(&path) {
        if let Ok(loaded) = serde_yaml::from_str::<RezCoreConfig>(&content) { config = loaded; break; }
        if let Ok(loaded) = serde_json::from_str::<RezCoreConfig>(&content) { config = loaded; break; }
    }
}
```

Search paths (`:141-191`): `<exe_dir>/rezconfig.{yaml,json}`, `$REZ_CONFIG_FILE`,
`/etc/rez/config.yaml` (unix) or `%PROGRAMDATA%/rez/config.yaml` (windows), then
`$HOME/{.rezconfig,.rezconfig.yaml,.rez/config.yaml}`. **No `rezconfig.py` execution** — only the
Python path (`config.py:1074-1088`) compiles and execs Python.

**Public singleton sources no files.** `crates/rez-next-python/python/rez_next/__init__.py:173`
is `config = Config()` with `filepaths=[]`, bypassing `_create_main_config()`
(`config.py:1353-1366`). The repo's own test acknowledges the shadowing
(`tests/test_config.py:9-10`).

**`config.override` is not a context manager** — `config.py:1267` lacks `@contextmanager`, so
upstream's `with config.override(...)` idiom raises `AttributeError: __enter__`.

**CLI:** `src/cli/commands/config.rs:10-25` — only `--json`, `--search-list`, `--source-list`, and
a positional `field`. Upstream `--source` and `--diff` are absent.

### rez spec side

Upstream `src/rez/config.py` declares the setting schema (`:397-540` region), with
`packages_path` `:397`, `platform_map` `:402`, `implicit_packages` `:408`, `memcached_uri` `:425`,
`local_packages_path` `:428`, `release_packages_path` `:429`, `default_shell` `:442`,
`resource_caching_maxsize` `:474`, `default_relocatable` `:520`, `package_filter` `:535`,
`package_orderers` `:536`. Upstream loads every file in its search path and **deep-merges** them,
supports `rezconfig.py` execution, package-local `_rezconfig.py`, `$REZ_HOME`, and
`config.override()` as a context manager.

### 判定

| Aspect | 判定 |
|---|---|
| `packages_path`, `local_packages_path`, `release_packages_path`, `plugin_path`, `tmpdir`, `editor`, `image_viewer`, `browser`, `difftool` | `ALIGNED` (present in the binary's config) |
| The other ~120 upstream settings (`implicit_packages`, `parent_variables`, `resetting_variables`, `env_var_separators`, `platform_map`, `default_relocatable`, `build_directory`, `context_tmpdir`, `release_hooks`, `package_filter`, `package_orderers`, …) | `GAP (needs rez-next work)` — Python-side defaults with **no Rust consumer** |
| Multi-file deep merge | `GAP (needs rez-next work)` — breaks on first parseable file |
| `rezconfig.py` execution (Rust side) | `GAP (needs rez-next work)` — YAML/JSON only |
| `config.override()` context manager | `GAP (needs rez-next work)` — not decorated |
| `rez config --source` / `--diff` | `GAP (needs rez-next work)` |
| `package_repository_config`, `all_parent_settings`, `rez_tools_path`, `rezgui_path`, `show_hidden_packages`, `package_ignore_regex`, `$REZ_HOME`, package-local `_rezconfig.py` | `GAP (needs rez-next work)` — absent repo-wide |

### VX impact

**NON-BLOCKING** for the four stated VX needs — `packages_path`, `local_packages_path` and
`release_packages_path` are all present in the binary's config. It becomes relevant if VX relies on
`implicit_packages` or `platform_map` for cross-platform resolution.

---

## B10. `rez status` / `rez help` / other top-level commands

- **`rez status`** — `src/cli/commands/status.rs:13-49`. Package status is real (`:151`), repo
  status is approximate (`:200`, `:384`, counts subdirectories as packages, `family_count =
  package_count` with a `// Simplified` comment at `:416`). `--families` and the default overview
  are broken by the `find_packages("")` bug (`:254`, `:321`). `--recent` and `--issues` are dead
  flags. **`GAP`.**
- **`rez pkg-help`** (`src/cli/commands/help.rs:12-36`) — **STUB.** It synthesises three sections
  (`Description`, `Package Information`, `Usage`) from fields it already has
  (`:237-278`) and **never reads the real `Package::help` field**. Upstream
  `src/rez/cli/help.py` renders the package's `help` triple-quoted string and supports
  `-m/--manual` and `-e/--entries`. Note `setup_repositories` hardcodes
  `vec![PathBuf::from("./local_packages")]` (`:174-175`) instead of config `packages_path`.
  **`GAP`.**
- **`rez gui`** — not a GUI. `src/cli/commands/gui.rs:3-4` states: *"In rez-next, we implement this
  as an HTML report generator since we don't have a Qt/PySide dependency."* **`INTENTIONAL
  DEVIATION`.**
- **`rez self-update`** — real, with mandatory SHA-256 verification
  (`src/cli/commands/self_update.rs:371-400`, `:457-475`). Two notes: on Windows it cannot
  self-replace and prints manual `move /Y` instructions (`:272-289`); and the hardcoded repo is
  `const REPO: &str = "loonghao/rez-next";` (`:16`), which does **not** match the manifest's
  `repository = "https://github.com/vx-org/rez-next"` (`Cargo.toml:32`). **Not an upstream
  command;** flag the repo-const mismatch as a defect.
- **`rez selftest`, `rez parse-version`** — dev utilities, not upstream commands.

---

## B11. CLI command coverage table

**rez-next top-level surface.** Two binaries only — `Cargo.toml:84-90` (`rez-next` →
`src/bin/rez-next.rs`, `rez` → `src/bin/rez.rs`, which is a 1-line `include!`). No
`[project.scripts]` / console_scripts anywhere in the repo
(`crates/rez-next-python/pyproject.toml` has `[build-system]` + `[project]` + `[tool.maturin]`
only). Six additional binaries under `crates/*/src/bin/` are dev/bench harnesses, auto-discovered
by cargo, not user-facing CLI.

The 28 subcommands are enumerated at `src/cli/mod.rs:47-147`.

| Upstream `rez` command / script | rez-next counterpart | Status |
|---|---|---|
| `rez` | `rez` / `rez-next` (clap root, `src/cli/mod.rs:17`) | ALIGNED |
| `rezolve` (macOS alias) | — | GAP (no counterpart) |
| `_rez-complete` | `rez complete` (subcommand) | ALIGNED (shape differs: subcommand vs script) |
| `_rez_fwd` | `rez forward` (`src/cli/commands/forward.rs:12`) | ALIGNED |
| `rez-bind` | `rez bind` (`mod.rs:73`) | GAP — 12 hardcoded binders, no plugin discovery |
| `rez-build` | `rez build` (`mod.rs:67`) | ALIGNED (real; 5 dead flags) |
| `rez-config` | `rez config` (`mod.rs:49`) | GAP — 19 of ~141 settings; no `--source`/`--diff` |
| `rez-context` | `rez context` (`mod.rs:52`) | GAP — 5 dead flags; `--interpret` heuristic |
| `rez-cp` | `rez cp` (`mod.rs:82`) | GAP — no `--keep-timestamp`/`--variants`/`--shallow`/`--rename`/`--reversion` |
| `rez-depends` | `rez depends` (`mod.rs:76`) | GAP — no console script; always returns empty (`find_packages("")`) |
| `rez-diff` | `rez diff` (`mod.rs:94`) | GAP — `modified` hardcoded `[]`; JSON hand-printed; `--metadata-only` dead |
| `rez-env` | `rez env` (`mod.rs:58`) | ALIGNED (10 dead flags; no `-o/--output`) |
| `rez-gui` | `rez gui` (`mod.rs:123`) | INTENTIONAL DEVIATION — HTML report, not a GUI |
| `rez-help` | `rez pkg-help` (`mod.rs:97`) | GAP — stub; never reads `Package::help` |
| `rez-interpret` | — | GAP (no counterpart; `rez context --interpret` is a weak substitute) |
| `rez-memcache` | — | GAP (no counterpart; memcached absent) |
| `rez-pip` | `rez pip` (`mod.rs:114`) | GAP — shell-out only; Python `rez_next.pip` is a stub |
| `rez-pkg-cache` | `rez pkg-cache` (`mod.rs:104`) | ALIGNED |
| `rez-pkg-ignore` | `rez rm --ignored-since` (partial) | GAP — no dedicated command; the `rm` variant is broken (`rm.rs:301`) |
| `rez-plugins` | `rez plugins` (`mod.rs:101`) | GAP — stub; heuristic substring matching |
| `rez-python` | — | GAP (no counterpart) |
| `rez-release` | `rez release` (`mod.rs:61`) | GAP — git only (`ensure_supported_vcs`, `release.rs:242`); 3 dead flags |
| `rez-search` | `rez search` (`mod.rs:70`) | ALIGNED (QUERY required, unlike upstream) |
| `rez-selftest` | `rez self-test` (`mod.rs:142`) | ALIGNED (dev smoke test) |
| `rez-status` | `rez status` (`mod.rs:91`) | GAP — `--families`/overview always report 0 |
| `rez-suite` | `rez suites` (`mod.rs:108`) | ALIGNED (8 subcommands) |
| `rez-test` | `rez test` (`mod.rs:64`) | ALIGNED (real, full) |
| `rez-view` | `rez view` (`mod.rs:55`) | ALIGNED (`package.py` only) |
| `rez-yaml2py` | — | GAP (absent repo-wide) |
| `rez-bundle` | `rez bundle` (`mod.rs:111`) | ALIGNED (resolve failure downgraded to warning, `:156-165`) |
| `rez-benchmark` | — | GAP (no counterpart) |
| `rez-mv` | `rez mv` (`mod.rs:85`) | GAP — copy+delete, not atomic; no `--keep-timestamp` |
| `rez-rm` | `rez rm` (`mod.rs:88`) | GAP — `--ignored-since` broken; `-f` means `--family` |
| — (rez-next extra) | `rez solve` (`mod.rs:79`) | N/A (rez-next extension, real) |
| — (rez-next extra) | `rez self-update` (`mod.rs:145`) | N/A (rez-next extension, real) |
| — (rez-next extra) | `rez parse-version` (`mod.rs:136`) | N/A (dev utility) |

Upstream script list source: `src/rez/cli/_entry_points.py`, `@scriptname` decorators —
`rez rezolve _rez-complete _rez_fwd rez-bind rez-build rez-config rez-context rez-cp rez-depends
rez-diff rez-env rez-gui rez-help rez-interpret rez-memcache rez-pip rez-pkg-cache rez-plugins
rez-python rez-release rez-search rez-selftest rez-status rez-suite rez-test rez-view rez-yaml2py
rez-bundle rez-benchmark rez-pkg-ignore rez-mv rez-rm` (33 entries).

**Missing outright:** `rezolve`, `rez-interpret`, `rez-memcache`, `rez-python`, `rez-yaml2py`,
`rez-benchmark`, `rez-pkg-ignore` (7).

---

# PART C — VX impact summary

| VX need | Verdict | Blocking evidence |
|---|---|---|
| Filesystem package repository | **NON-BLOCKING** | `SimpleRepository` scans and resolves correctly (`simple_repository.rs:92-104`). **Caveat:** only `package.py` is recognised (`scanner_types.rs:12`) — verify VX emits `package.py`, not `package.yaml`. |
| Variant install | **BLOCKING** | `FilesystemPackageRepository::install_variant` returns `Err` (`package_repository/filesystem.rs:544-547`); `iter_variants` returns a single synthetic variant (`:315-325`). Only `rez build`/`rez release` can install variants, via `PackageInstallLayout` (`install_layout.rs:33`, wired at `builder.rs:287`, `release.rs:525`). No repository-level install entry point exists. |
| Package copy / publish | **BLOCKING** | `rez cp` is a blind `copy_dir_recursive` (`cp.rs:289-305`) that bypasses `install_variant`; no `--rename`/`--reversion`, no `--variants`, no relocatable check. Three divergent copy implementations. |
| Deterministic payloads | **BLOCKING** | No `--keep-timestamp` on `cp`/`mv` (upstream `src/rez/cli/cp.py:41-43`, `src/rez/cli/mv.py:16-18`); the Python `copy_package` explicitly raises on `keep_timestamp` (`package_copy.py:121-135`). |

---

# Candidate GitHub issues

Each entry is a proposed public-safe issue for `vx-org/rez-next`. Bodies contain no internal
identifiers, private paths, or Monica references.

---

### 1. Implement `FilesystemPackageRepository::install_variant`

`install_variant` currently returns an error, so there is no repository-level way to install a
package variant. Variant installation is only reachable through `rez build` / `rez release`, which
requires building from source.

The `PackageRepository` trait already declares the full upstream contract in
`crates/rez-next-repository/src/package_repository/mod.rs`, and
`crates/rez-next-package/src/install_layout.rs` already computes the canonical Rez variant subpath
(including hashed variants). What is missing is the write path: create the package base directory,
copy the variant payload to the computed subpath, apply `overrides` (including `name` / `version`
reversioning and the `REMOVE` sentinel), honour `dry_run`, and return the installed variant.

Upstream reference: `src/rezplugins/package_repository/filesystem.py::install_variant`, which also
takes a package lock during install and delegates payload copying to `_create_variant`.

Acceptance criteria: a prebuilt variant payload can be installed into an arbitrary filesystem
repository without a build step; `dry_run` returns the would-be variant without writing;
`overrides` support rename and reversion.

---

### 2. Wire `rez cp` / `rez mv` through the repository install path and add `--keep-timestamp`

`rez cp` performs a naive recursive directory copy and never calls the repository install hook. It
also lacks several upstream flags, most importantly `--keep-timestamp`, which matters for
reproducible package distribution: without it, every copy rewrites file mtimes to copy time.

There are three divergent copy implementations today: the CLI's own `copy_dir_recursive`, the
`rez-next-package` domain `copy_package`, and the Python `rez_next.package_copy` wrapper — each
with a different flag set, and the Python wrapper actively raises on
`shallow` / `keep_timestamp` / `variants` / `dry_run`.

Proposed work: converge on the domain implementation, route it through
`PackageRepository::install_variant`, and add the upstream flag surface
(`--keep-timestamp`, `--variants`, `--shallow`, `--follow-symlinks`, `--rename`,
`--reversion`, `--allow-empty`, `--dest-path`, `-p/--paths`).

Upstream reference: `src/rez/cli/cp.py` and `src/rez/package_copy.py`.

---

### 3. Make the upstream-faithful `PackageRepository` reachable from the Rust CLI

The repository crate contains two filesystem repository implementations. The upstream-faithful one
(`package_repository::FilesystemPackageRepository`, with the full 14-method
`PackageRepository` trait) is only exposed through the PyO3 bindings; every Rust consumer — the
CLI, the solver, the runtime — uses `simple_repository::SimpleRepository`, a 5-method trait with no
variant, install, remove, or resource-handle surface.

This is why features that logically belong to the repository (variant install, ignore markers,
payload paths, repository-level remove) behave differently depending on whether they are invoked
from Python or from the CLI.

Proposed work: consolidate on one implementation, or document the split and bridge the CLI to the
full trait. Also implement the `Memory` repository type, which currently exists only as an enum
variant (`crates/rez-next-repository/src/repository.rs:35`).

---

### 4. Support `type@location` repository specs and variant URI suffixes

Upstream `packages_path` entries may be `type@location`, where `type` selects the package
repository plugin (`src/rez/package_repository.py::PackageRepositoryManager.get_repository`).
rez-next treats every entry as a literal directory path, so such a config silently resolves to a
non-existent directory instead of failing or dispatching.

Related: upstream variant URIs carry an index suffix,
`/{repo}/{name}/{version}/package.py[{index}]` (`src/rez/packages.py:843`). rez-next's
`get_package_from_uri` does not parse it, and `get_variant_from_uri` /
`get_variant` raise `NotImplementedError`.

Proposed work: parse `type@location` in `packages_path`, dispatch on the type, and fail loudly on
an unknown type; parse the `[index]` suffix in URI resolution.

---

### 5. Add missing shell emitters and consolidate shell dispatch

Five shells are implemented (bash, zsh via the bash emitter, fish, cmd, powershell). Missing
relative to upstream `src/rezplugins/shell/`: `sh`, `csh`, `tcsh`, `gitbash`, and `pwsh` (currently
a parse alias rather than a distinct shell).

Two further problems make this more than a "add a match arm" task: shell behaviour is spread across
roughly fourteen hardcoded `match` sites over two duplicated `ShellType` enums
(`rez-next-context` and `rez-next-rex`), and there are three independent emitters that disagree on
quoting and on fish syntax (`set -gx` vs `set -x`).

Also: `default_shell` is read nowhere — it is defined, printed by `rez config`, and ignored by
`rez env`.

Proposed work: introduce a `Shell` trait with one emitter, register the nine upstream shells
behind it, delete the duplicate enums, and wire `default_shell` plus `$SHELL` detection into
`rez env`.

---

### 6. Make `rez plugins` query a real registry

`rez plugins` currently prints a hardcoded banner and then infers "plugins" by substring-matching
package fields — `discover_extension_plugins` literally checks whether the package name contains
the word "plugin". Nothing loads plugin modules or reads entry points.

Separately, `crates/rez-next-repository/src/package_search.rs::get_plugins` is a real
implementation that scans for `plugin_for`, but `rez plugins` does not call it. The Python-side
`plugin_managers.py` is a faithful port whose two discovery paths are both dead (it imports a
`rezplugins` namespace that does not exist, and reads an entry-point group nothing declares).

Proposed work: have `rez plugins <pkg>` call the existing `get_plugins` scan, and implement real
plugin-type registration and discovery so third-party `package_repository` / `release_hook`
plugins can be loaded.

---

### 7. Fix `find_packages("")` call sites — `rez depends` and `rez status` always return empty

`find_packages` is an exact cache-key lookup
(`crates/rez-next-repository/src/simple_repository.rs:162-163`), so `find_packages("")` always
returns an empty vector. Three call sites rely on it as an "enumerate everything" idiom:
`rez depends` (reverse-dependency lookup), `rez status --families`, and bare `rez status`.

The practical result is worse than a missing feature: `rez depends` prints "No packages depend on
X" and exits 0, so a wrong answer looks like a clean one. `rez search` already does this correctly
via `list_packages()`.

Proposed work: replace the empty-string idiom with `list_packages()` plus per-name lookup (as the
Python bindings already do), and add a regression test that a package with a known dependent is
reported by `rez depends`.

---

### 8. Add `yaml2py` and decide the `package.yaml` story

`yaml2py` is absent — there is no `rez-yaml2py` script, no `rez_next.utils` package, and no
conversion entry point anywhere in the repo.

This interacts with an inconsistency: the build path recognises `package.yaml`
(`crates/rez-next-package/src/developer_package.rs:111`), but the repository scanner recognises
only `package.py` (`crates/rez-next-repository/src/scanner_types.rs:12`,
`REZ_PACKAGE_FILENAMES = &["package.py"]`). A package authored in YAML is therefore buildable but
invisible to resolution.

Proposed work: either add `package.yaml` / `package.txt` to `REZ_PACKAGE_FILENAMES` (matching
upstream `rez/serialise.py::FileFormat`), or ship `yaml2py` so YAML definitions can be converted
ahead of publication. Both would be ideal; at minimum, emit a warning when a scan skips a
`package.yaml`.

---

### 9. Collapse the three config systems into one

Three configuration systems coexist and do not read each other's files or share a schema:

- `RezCoreConfig` (19 fields) — used by the binary; YAML/JSON only; breaks on the first parseable
  file rather than merging.
- `rez-next-config::Config` (generic JSON tree) — exposed to Python only; not referenced by the
  binary.
- `rez_next.config.Config` (141 schema keys) — Python only; the only one that executes
  `rezconfig.py`.

Consequences: roughly 120 upstream settings are inert when running the Rust binary, including
`implicit_packages`, `parent_variables`, `resetting_variables`, `env_var_separators`,
`platform_map`, `default_relocatable`, `build_directory`, `context_tmpdir`, `package_filter` and
`package_orderers`. `config.override()` is also missing its `@contextmanager` decorator, so the
common upstream `with config.override(...)` idiom raises.

Proposed work: pick one schema, load and deep-merge every file in the search path the way upstream
does, and make `rezconfig.py` execution available to the binary.

---

### 10. Remove or implement the inert `memcached_*` settings

`memcached_uri` and the four `memcached_*_min_compress_len` settings are declared in the Python
config module and its schema, but nothing reads them: there is no memcached client crate, no
Python dependency, and `rez_next/serialise.py` documents its memcache path as a no-op.

Silently ignoring a setting is worse than rejecting it — a studio migrating from upstream Rez can
set `memcached_uri` and believe caching is active.

Proposed work: either implement the caching layer (note that `rez-next-package-cache::FileCache` is
a working mtime-invalidated persistent cache that is currently unwired), or drop the settings and
log a warning when one is present in a config file.

---

### 11. Fix `rez bind` binder tables and add a real discovery mechanism

The crate declares twelve binders (`crates/rez-next-bind/src/builtin_binders.rs`) while the CLI
detector (`src/cli/commands/bind/detect.rs`) handles a different set of eleven names. Six declared
binders (`node`, `rust`, `go`, `java`, `ffmpeg`, `imagemagick`) cannot be detected, and five
detectable ones are absent from the crate table.

On a detection miss the version silently falls back to `1.0.0` rather than failing, and
`-l/--list` returns a hardcoded array with synthetic `builtin://` paths instead of enumerating real
bind modules.

Upstream reference: `src/rez/bind/` (14 binders, discovered as modules).

Proposed work: make the crate table and the detector share one source of truth, add real module
discovery, and error — rather than default to `1.0.0` — when a tool cannot be detected.

---

### 12. Add the missing upstream top-level commands (or document their omission)

Seven upstream commands have no counterpart: `rezolve`, `rez-interpret`, `rez-memcache`,
`rez-python`, `rez-yaml2py`, `rez-benchmark`, and `rez-pkg-ignore`. The remaining upstream
commands exist as clap subcommands rather than console scripts, because the project declares no
`[project.scripts]` and ships only two binaries.

This matters for drop-in adoption: scripts and CI that invoke `rez-pip` or `rez-search` directly
will not find them. (Shell-completion output also lists four commands that do not exist —
`interpret`, `benchmark`, `source`, and a misspelled `selftest`.)

Proposed work: add a thin dispatcher that installs the upstream `rez-*` script names as aliases for
the corresponding subcommands, and regenerate completion lists from the command enum rather than a
hand-maintained array.

---

## Appendix — evidence commands used

```bash
# rez-next HEAD / version
git -C <rez-next> rev-parse --short HEAD          # 97eef03
cat <rez-next>/.release-please-manifest.json      # { ".": "0.3.10" }

# upstream Rez HEAD
gh api repos/nerdvegas/rez/commits/main --jq '.sha[0:12]'   # f622b817ef63

# upstream directory listings (authoritative for the paths cited as "rez spec side")
gh api repos/nerdvegas/rez/contents/src/rez/cli                      --jq '.[].name'
gh api repos/nerdvegas/rez/contents/src/rezplugins                   --jq '.[].name'
gh api repos/nerdvegas/rez/contents/src/rezplugins/package_repository --jq '.[].name'
gh api repos/nerdvegas/rez/contents/src/rezplugins/shell             --jq '.[].name'
gh api repos/nerdvegas/rez/contents/src/rez/bind                     --jq '.[].name'

# rez-next absence proofs (all returned 0 matches, run from the rez-next root)
grep -rn "split_once('@')"          --include=*.rs .
grep -rn "://"                      --include=*.rs crates/rez-next-repository/src
grep -rn '"s3"'                     --include=*.rs .
grep -rni "gitbash"                 --include=*.rs --include=*.toml --include=*.py .
grep -rni "yaml2py"                 .
grep -rn "\[project.scripts\]"      --include=*.toml .
grep -rn "rez_next_package_cache"   --include=*.rs .
```

`upstream-side` items that could not be verified from source are marked `UNVERIFIED` inline
(the published format of `vx-rez-packages` package definitions, whose working copy in this
worktree contains no package files).
