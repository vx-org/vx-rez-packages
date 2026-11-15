# D. Repository & distribution

## 19. `package_repository` plugin family

### 19.1 Plugin modules

In Rez 3.4.0 there are exactly **two** `package_repository` plugin modules:

| Module | Plugin class | `name()` | Purpose |
|---|---|---|---|
| `src/rezplugins/package_repository/filesystem.py` | `FileSystemPackageRepository` (`:438`), `name()` at `:490-492` → `"filesystem"` | `filesystem` | Packages stored on disk as `package.py` / `package.yaml` in `/LOCATION/pkgA/1.0.0/package.py` layout, or as "combined" per-family files `/LOCATION/pkgC.yaml` (`:445-473`). Registered via `register_plugin()` at `:1545-1546`. |
| `src/rezplugins/package_repository/memory.py` | `MemoryPackageRepository` (`:115`), `name()` at `:143-145` → `"memory"` | `memory` | Packages held in a plain dict; used for developer packages and `PackageMaker`-created packages (`:24-26`). Registered via `register_plugin()` at `:210-211`. |

Supporting members of the directory:

* `src/rezplugins/package_repository/__init__.py:5-6` — namespace extension,
  `__path__ = extend_path(__path__, __name__)` (§A.1.4).
* `src/rezplugins/package_repository/rezconfig.py:5-47` — plugin defaults for `filesystem`:
  `file_lock_type` (`:9`), `file_lock_timeout` (`:15`), `file_lock_dir` (`:27`),
  `check_package_definition_files` (`:33`), `package_filenames` (`:45-47`).

`FileSystemPackageRepository` registers six resource classes in its `__init__`
(`src/rezplugins/package_repository/filesystem.py:527-533`): `FileSystemPackageFamilyResource`
(`:93`, key `filesystem.family` at `:94`), `FileSystemPackageResource` (`:140`, key
`filesystem.package` at `:141`), `FileSystemVariantResource` (`:272`, key `filesystem.variant` at
`:273`), and three "combined" variants (`:288`, `:353`, `:416`). `MemoryPackageRepository` registers
three (`src/rezplugins/package_repository/memory.py:176-178`): `MemoryPackageFamilyResource` (`:33`),
`MemoryPackageResource` (`:62`), `MemoryVariantResource` (`:93`).

Runtime enumeration: `get_package_repository_types()` — `src/rez/package_repository.py:26-28`.

### 19.2 The plugin contract

**Correction to a common assumption:** `src/rez/package_repository.py` defines **only three**
classes — `PackageRepositoryGlobalStats` (`:46`), `PackageRepository` (`:69`),
`PackageRepositoryManager` (`:526`). The classes named `Package` and `Variant` are **not** in this
file; they live in `src/rez/packages.py:203` and `src/rez/packages.py:342`. Their repository-level
counterparts are the *resource* classes in `src/rez/package_resources.py`:
`PackageRepositoryResource` (`:275`), `PackageFamilyResource` (`:315`), `PackageResource` (`:324`),
`VariantResource` (`:346`), `PackageResourceHelper` (`:397`), `VariantResourceHelper` (`:470`).

Second correction: **`PackageRepository` is not an ABC** — no `abc` import, no `ABCMeta`, no
`@abstractmethod` in `src/rez/package_repository.py`. Abstractness is expressed by
`raise NotImplementedError` bodies.

`PackageRepositoryGlobalStats` (`src/rez/package_repository.py:46`) is a `threading.local`
subclass holding process-wide load timing: `__init__` (`:49-52`) sets `package_load_time = 0.0`
(`:52`); `package_loading()` (`:54-63`) is a `@contextmanager` accumulating into it. Instantiated as
the module global `package_repo_stats` (`:66`).

`PackageRepository` — `src/rez/package_repository.py:69`. Concrete members:

| Member | Line | Notes |
|---|---|---|
| `remove = object()` | `:79` | Sentinel: set an override value to this to *delete* an attribute during `install_variant` (documented `:344-347`). |
| `__init__(location, resource_pool)` | `:86-95` | Sets `self.location` (`:94`), `self.pool` (`:95`). |
| `__str__` | `:97-98` | `"%s@%s" % (self.name(), self.location)` — the canonical URI form. |
| `register_resource(resource_class)` | `:100-106` | Subclass `__init__` must call this per resource type. |
| `clear_caches()` | `:108-110` | |
| `uid` (`@cached_property`) | `:112-122` | Must be a *persistent* identifier (`:114-120`). |
| `__eq__` | `:124-129` | Compares `name()` and `uid`. |
| `is_empty()` | `:131-141` | |
| `get_package(name, version)` | `:186-204` | Concrete default via `get_package_family` + scan. |
| `get_package_from_uri(uri)` | `:206-216` | Concrete, returns `None` (`:216`). |
| `get_variant_from_uri(uri)` | `:218-228` | Concrete, returns `None` (`:228`). |
| `get_equivalent_variant(variant_resource)` | `:355-372` | Concrete; `install_variant(variant_resource, dry_run=True)` (`:372`). |
| `pre_variant_install(variant_resource)` | `:304-313` | Concrete no-op (`:313`). |
| `on_variant_install_cancelled(variant_resource)` | `:315-328` | Concrete no-op (`:328`). |
| `get_variant_state_handle(variant_resource)` | `:396-411` | Concrete, returns `None` (`:411`). |
| `get_last_release_time(package_family_resource)` | `:413-426` | Concrete, returns `0` (`:426`). |
| `make_resource_handle(...)` | `:428-450` | Enforces `repository_type` (`:435-440`) and `location` (`:442-446`). |
| `get_resource(...)` | `:452-466` | |
| `get_resource_from_handle(...)` | `:468-497` | |
| `_uid()` | `:511-523` | Default `(self.name(), self.location)` (`:523`). |

Every `PackageRepository` method that raises `NotImplementedError` (i.e. the plugin must implement it):

| Signature | Line |
|---|---|
| `name(cls) -> str` | `:82` |
| `get_package_family(self, name) -> PackageFamilyResource \| None` | `:143` |
| `iter_package_families(self) -> Iterator[PackageFamilyResource]` | `:154` |
| `iter_packages(self, package_family_resource) -> Iterator[PackageResource]` | `:163` |
| `iter_variants(self, package_resource) -> Iterator[VariantResource]` | `:175` |
| `ignore_package(self, pkg_name, pkg_version, allow_missing=False) -> int` | `:230` |
| `unignore_package(self, pkg_name, pkg_version) -> int` | `:249` |
| `remove_package(self, pkg_name, pkg_version) -> bool` | `:262` |
| `remove_package_family(self, pkg_name, force=False) -> bool` | `:277` |
| `remove_ignored_since(self, days, dry_run=False, verbose=False) -> int` | `:289` |
| `install_variant(self, variant_resource, dry_run=False, overrides=None) -> VariantResource` | `:330-333` |
| `get_parent_package_family(self, package_resource) -> PackageFamilyResource` | `:374` |
| `get_parent_package(self, variant_resource) -> PackageRepositoryResource` | `:385` |
| `get_package_payload_path(self, package_name, package_version=None) -> str` | `:499` |

Return-code contract for the ignore family: `-1` not found, `0` nothing done (already in that state),
`1` changed — `src/rez/package_repository.py:243-246`, `:256-258`.

**Class attributes subclasses set.** The repository class itself declares only `remove` (`:79`).
Required overrides: `name()`; resource classes carry `key`, `repository_type` and (for
package/variant) `schema` — e.g. `FileSystemPackageResource` has `key = "filesystem.package"`
(`filesystem.py:141`), `variant_key = "filesystem.variant"` (`:142`),
`repository_type = "filesystem"` (`:143`), `schema = package_pod_schema` (`:144`);
`MemoryPackageResource` mirrors this at `memory.py:63-66`. Repository sub-settings are declared as
`schema_dict` — `FileSystemPackageRepository.schema_dict` (`filesystem.py:474-477`).
`FileSystemPackageRepository` additionally sets `building_prefix = ".building"` (`:479`),
`ignore_prefix = ".ignore"` (`:480`), `package_file_mode` (`:482-488`, `None` on Windows).

**`build_time` as a repository attribute — ABSENT.** Searched: `grep -rn "build_time" src/`
(only vendored `distlib`: `src/rez/vendor/distlib/database.py:322`,
`src/rez/vendor/distlib/locators.py:1208`, `:1291`, `:1292`). See §A.9.

**`package_config_requires_parsing` — ABSENT.** Searched: `grep -rn
"package_config_requires_parsing" src/` → zero hits.

### 19.3 URI scheme and `packages_path` mapping

The separator is a single **`@`**, split with `maxsplit=1`. There is **no `|` options separator** —
ABSENT — searched: `grep -rn "split('|')\|split(\"|\")"` across `src/rez/` excluding `vendor/`; the
only `|` splitting in the tree is version-range parsing (`src/rez/version/_version.py:738`, `:1331`).

`PackageRepositoryManager.get_repository(path)` — `src/rez/package_repository.py:549-586`:

```python
# src/rez/package_repository.py:562-576
# normalise repo path
parts = path.split("@", 1)
if len(parts) == 1:
    parts = ("filesystem", parts[0])

repo_type, location = parts
if repo_type == "filesystem":
    # choice of abspath here vs realpath is deliberate. Realpath gives
    # canonical path, which can be a problem if two studios are sharing
    # packages, and have mirrored package paths, but some are actually
    # different paths, symlinked to look the same. It happened!
    #
    location = os.path.abspath(location)

normalised_path = "%s@%s" % (repo_type, location)
```

* **Default plugin:** an entry with no `@` splits into 1 part and defaults to **`"filesystem"`**
  (`src/rez/package_repository.py:563-565`). So `/foo/bar` → `filesystem@/foo/bar`, and
  `memory@123` → plugin `memory`, location `123`.
* `filesystem` locations use `os.path.abspath`, deliberately *not* `realpath` (comment `:569-573`).
* The normalised string is the cache key into `self.repositories` (`:578-584`), initialised at `:547`.
* `_get_repository(path, **repo_args)` (`:652-656`) re-splits on `'@'` (`:653`), resolves the class
  via `plugin_manager.get_plugin_class('package_repository', repo_type)` (`:654`), and constructs
  `cls(location, self.pool, **repo_args)` (`:655`).
* `are_same(path_1, path_2)` (`:588-603`) compares `uid`, not strings (`:603`).
* Singleton: `package_repository_manager = PackageRepositoryManager()` (`:660`).
* Pool sizing: `__init__` reads `config.resource_caching_maxsize`, mapping `-1` → `None` (`:539-544`).

`packages_path` is a `PathList` (`src/rez/config.py:397`) over `StrList` = `Schema([str])`
(`src/rez/config.py:187`) with `sep = os.pathsep` (`:223`) for env-var parsing. Stock value is the
three-entry list at `src/rez/rezconfig.py:62-66`.

`FileSystemPackageRepository` extends `_uid()` to include the inode, since a path alone is not a
stable identity across machines — `src/rezplugins/package_repository/filesystem.py:559-564`.

## 20. `package_filter` and `package_order` — **not** plugin families in 3.4.0

Both are config-driven, and **neither is a plugin type**. The seven registered plugin types
(`src/rez/plugin_managers.py:543-549`, §A.1.4) contain neither name — ABSENT — searched:
`grep -n "package_filter\|package_order" src/rez/plugin_managers.py` → zero hits. There is no
`PackageFilterPluginType` and no `PackageOrderPluginType`. Orderer extension is by **in-process class
registration** (`register_orderer`, `src/rez/package_order.py:751-765`), not plugin discovery.

### 20.1 `src/rez/package_filter.py`

| Class | Line | Role |
|---|---|---|
| `PackageFilterBase` | `:21` | Abstract-ish base (`raise NotImplementedError`, no `abc`). |
| `PackageFilter` | `:97` | One filter = a set of exclusion + inclusion rules. |
| `PackageFilterList` | `:234` | List of filters; a package is excluded iff **any** filter excludes it (`:236-238`). |
| `Rule` | `:333` | Base rule. |
| `RegexRuleBase` | `:436` | Shared regex machinery (`cost` 10 at `:443-444`). |
| `RegexRule` | `:455` | `name = "regex"` (`:460`). |
| `GlobRule` | `:473` | `name = "glob"` (`:478`). |
| `RangeRule` | `:491` | `name = "range"` (`:497`). |
| `TimestampRule` | `:519` | `name = "timestamp"` (`:541`); labels `before(...)` / `after(...)`. |

`PackageFilter` semantics (`:113-140`): quick-out if no excludes (`:114-115`); rules are looked up by
`package.name` then by the family-agnostic `None` bucket (`:124-128`); **a package is excluded only
if it matches ≥1 exclusion rule and no inclusion rule** (`:130-140`, docstring `:105-107`).
`cost` (`:170-186`) sums exclusion-rule costs, dividing family-specific ones by 10 (`:183-184`);
rules are cost-sorted on insert (`:220`). `__and__` combines filters (`:158-165`).

`PackageFilterList`: `add_filter` keeps the list cost-sorted (`:250`); `add_exclusion` appends to the
*last* (most expensive) filter (`:252-259`); `add_inclusion` applies across **all** filters
(`:261-270`); `excludes` returns the first matching rule (`:272-282`).
`PackageFilterList.singleton` is a `cached_class_property` built from `config.package_filter`
(`:319-326`). Module-level `no_filter = PackageFilterList()` (`:330`).

Rule parsing — `Rule.parse_rule(txt)` (`:363-401`):

```python
# src/rez/package_filter.py:375-394
types: dict[str, type[Rule]] = {
    "glob": GlobRule,
    "regex": RegexRule,
    "range": RangeRule,
    "before": TimestampRule,
    "after": TimestampRule,
}

label, txt = Rule._parse_label(txt)
if label is None:
    if "*" in txt:
        label = "glob"
    else:
        label = "range"
elif label not in types:
    raise ConfigurationError("'%s' is not a valid package filter type" % label)
```

A bare string containing `*` is a glob; otherwise a range. `TimestampRule` costs 1000 because it
forces a package load (`:568-570`); it supports `family` scoping (`family_re` `:432`), `reverse`
(`after`), and `match_untimestamped` (`:543-566`), with `after()`/`before()` constructors
(`:572-578`).

**`ExclusionRule`, `IntersectionRule`, `UnionRule`, `PackageFilterRule`, `RegexFilterRule`,
`GlobFilterRule` are all ABSENT.** Searched: full read of `src/rez/package_filter.py` plus
`grep -rn "ExclusionRule\|IntersectionRule\|UnionRule" src/` (zero hits outside `vendor/`).
Inclusion/exclusion is *not* a rule class — it is the dict a rule is stored in (`_excludes` vs
`_includes`, `:110-111`), selected by `add_exclusion()` / `add_inclusion()`. The rule base class is
named `Rule` (`:333`).

Serialisation: `to_pod` emits `{"excludes": [...], "includes": [...]}` (`:206-215`); `from_pod`
accepts a single string or a list per namespace (`:198-201`). `sha1` is a hash of `str(self)`
(`:83-91`).

Config key: `"package_filter": OptionalDictOrDictList` — `src/rez/config.py:535`; type defined
`src/rez/config.py:322-326`; default `package_filter = None` (`src/rez/rezconfig.py:453`), documented
with the full rule table at `src/rez/rezconfig.py:401-452`. Consumers include
`src/rez/package_filter.py:326`, `src/rez/build_process.py:277-288`.

### 20.2 `src/rez/package_order.py`

| Class | Line | `name` | Purpose |
|---|---|---|---|
| `FallbackComparable` | `:26` | — | Compares via `main_comparable`, falls back on exception (`:37-47`). |
| `PackageOrder` | `:53` | `None` (`:57`) | Base reorderer. |
| `NullPackageOrder` | `:205` | `no_order` (`:212`) | No-op; returns `0` for every key (`:214-217`). |
| `SortedOrder` | `:243` | `sorted` (`:246`) | Sort by `Package.version`; `descending` flag (`:248-263`). |
| `PerFamilyOrder` | `:297` | `per_family` (`:300`) | Different orderer per family plus a `default_order` (`:302-341`). |
| `VersionSplitPackageOrder` | `:415` | `version_split` (`:421`) | Versions `<= first_version` first (`:415-419`, `:432-434`). |
| `TimestampPackageOrder` | `:468` | `soft_timestamp` (`:509`) | Prefer packages before `timestamp`, allow changes at/above `rank`. |
| `PackageOrderList` | `:635` | — | `List[PackageOrder]` with a family→orderer index. |

`PackageOrder` contract: `packages` property (`:67-85`, `None` → `[ALL_PACKAGES]`, `ALL_PACKAGES =
"*"` at `:23`); `reorder(iterable, key=None)` (`:87-113`) — note the documented distinction between
returning `None` (pass to next orderer) and returning a list (`:94-98`);
`sort_key(package_name, version_like)` (`:128-165`); and the single method a subclass must implement,
`sort_key_implementation(package_name, version)` (`:167-179`). Also abstract-by-`NotImplementedError`:
`to_pod` (`:181-182`), `from_pod` (`:184-186`).

`PackageOrderList.singleton` is built from `config.package_orderers` (`:655-658`); `refresh()` builds
`by_package` so **earlier orderers win** (`:666-676`); `get()` lazily refreshes via a `dirty` flag
(`:707-715`).

Dispatch and default:

```python
# src/rez/package_order.py:739-748
def get_orderer(package_name, orderers=None) -> PackageOrder:
    if orderers is None:
        orderers = PackageOrderList.singleton
    orderer = orderers.get(package_name)
    if orderer is None:
        orderer = orderers.get(ALL_PACKAGES)
    if orderer is None:
        # default ordering is version descending
        orderer = SortedOrder(descending=True)
    return orderer
```

`register_orderer(cls)` (`:751-765`) admits any `PackageOrder` subclass with a truthy `name`;
builtins are auto-registered by scanning module globals (`:768-771`).

**`VersionOrderer`, `TimestampOrderer`, `SortKeyOrderer` are ABSENT** — searched: full read of
`src/rez/package_order.py` (771 lines); `grep -rn "VersionOrderer\|TimestampOrderer\|SortKeyOrderer"
src/` → zero hits outside `vendor/`. The modern equivalents are `SortedOrder` (`:243`) and
`TimestampPackageOrder` (`:468`). `PerFamilyOrder` *does* exist, under that exact name (`:297`).

**There is no `package_order` config key** — ABSENT — searched
`grep -rn '"package_order"' src/` excluding `vendor/` → zero hits. The key is
`"package_orderers": OptionalDictOrDictList` (`src/rez/config.py:536`), default `None`
(`src/rez/rezconfig.py:459`). Anyone migrating a pre-3.x config must rename `package_order` →
`package_orderers`.

## 21. `package_copy` / `package_move` / `package_remove`

All three are registered in the subcommand dict at `src/rez/cli/_util.py:24-73` (`"cp": {}` `:34`,
`"mv": {}` `:71`, `"rm": {}` `:72`) and exposed as hyphenated console scripts `rez-cp`
(`src/rez/cli/_entry_points.py:127`), `rez-mv` (`:309`), `rez-rm` (`:316`).

### 21.1 `rez cp` — `src/rez/cli/cp.py`

| Flag | Line | Meaning |
|---|---|---|
| `--dest-path PATH` | `:12-16` | Destination **repository** path. Defaults to the source package's own repository — only valid together with `--rename`/`--reversion`. |
| `--paths PATHS` | `:17-19` | Override package search path. |
| `--nl`, `--no-local` | `:20-22` | Don't search local packages. |
| `--reversion VERSION` | `:24-26` | Copy to a different package version. |
| `--rename NAME` | `:27-29` | Copy to a different package name. |
| `-o`, `--overwrite` | `:30-32` | Overwrite existing package/variants. |
| `-s`, `--shallow` | `:33-35` | Shallow copy — symlink topmost directories instead of copying payload. |
| `--follow-symlinks` | `:36-39` | Dereference symlinks when copying payload. |
| `-k`, `--keep-timestamp` | `:40-43` | Keep the source package's timestamp. Ignored when copying into an *existing* package. |
| `-f`, `--force` | `:44-46` | Copy even if the package is not relocatable ("use at your own risk"). |
| `--allow-empty` | `:47-49` | Permit a copy into an empty target repository (guards the "you passed a package dir, not a repo dir" mistake, `:138-150`). |
| `--dry-run` | `:50-52` | Dry-run mode. |
| `--variants INDEX [INDEX …]` | `:53-56` | Zero-indexed variant selection; negative indices count from the end. |
| `--variant-uri URI` | `:57-59` | Copy the variant with this URI; **ignores** `--variants`. |
| `PKG` (positional, optional) | `:60-62` | Package to copy. |

Validation: `PKG` XOR `--variant-uri` (`:79-83`); `--dest-path` required unless
`--rename`/`--reversion` (`:85-87`); ambiguous multi-match aborts with a listing (`:123-127`).

### 21.2 `rez mv` — `src/rez/cli/mv.py`

| Flag | Line | Meaning |
|---|---|---|
| `-d`, `--dest-path PATH` (**required**) | `:12-14` | Repository to move PKG into — mandatory for `mv`, unlike `cp`. |
| `-k`, `--keep-timestamp` | `:15-17` | Keep timestamp of source package. |
| `-f`, `--force` | `:18-20` | Move even if not relocatable. |
| `PKG` (positional, required) | `:21-23` | Package to move, e.g. `foo-1.2.3`. |
| `PATH` (positional, optional) | `:24-27` | The repository containing the package; if omitted, candidate repositories are printed and the command exits (`:34-53`, `:64-66`). |

### 21.3 `rez rm` — `src/rez/cli/rm.py`

The four target selectors form a **mutually exclusive group** (`src/rez/cli/rm.py:14`):

| Flag | Line | Meaning |
|---|---|---|
| `-p`, `--package` | `:15-18` | Remove the specified package (`foo-1.2.3`); works even if currently ignored. |
| `-f`, `--family` | `:19-22` | Remove a package family (`python`) — only if the family is empty. |
| `--force-family` | `:23-25` | Like `-f`, but delete the family even if not empty. |
| `-i`, `--ignored-since DAYS` (int) | `:26-28` | Remove all packages ignored for `>= DAYS`. |
| `--dry-run` | `:30-32` | Dry-run mode. |
| `PATH` (positional, optional) | `:33-36` | Repository containing the package(s)/family. |

**`--dry-run` support is partial and asymmetric:** it is **rejected** for `--package`
(`parser.error("--dry-run is not supported with --package")`, `:43-44`) and for
`--family`/`--force-family` (`:63-64`), but **supported** for `--ignored-since` (`:95-100`, printing
"N packages would be removed." at `:104`). **`--force` does not exist as a top-level `rm` flag** —
the force behaviour is the separate `--force-family` selector (`:23-25`).

### 21.4 API contract

**`copy_package`** — `src/rez/package_copy.py:31-44`:

```python
def copy_package(package: Package,
                 dest_repository: PackageRepository,
                 variants: list[int] | None = None,
                 shallow: bool = False,
                 dest_name: str | None = None,
                 dest_version: str | Version | None = None,
                 overwrite: bool = False,
                 force: bool = False,
                 follow_symlinks: bool = False,
                 dry_run: bool = False,
                 keep_timestamp: bool = False,
                 skip_payload: bool = False,
                 overrides=None,
                 verbose: bool = False) -> dict[str, list[tuple[Variant, Variant]]]:
```

Returns `{"copied": [(src_variant, dest_variant), …], "skipped": [(src_variant,
existing_dest_variant), …]}` (`:111-115`, documented `:53-68`). Semantics:

* **Relocatability gate** — raises `PackageCopyError` unless `force` or `skip_payload` (`:117-121`).
* **Destination** may be a `PackageRepository` or a path string (`:123-127`).
* **Self-copy guard** — raises if source repo == dest repo and neither name nor version changes
  (`:129-135`).
* **Variant selection** via `resolve_variant_indices` (`:138-144`, helper `src/rez/util.py:195-215`);
  `None` means all (`:146-149`); empty selection returns immediately (`:151-152`).
* **`--overwrite`** — existence is probed with `install_variant(..., dry_run=True)` (`:168-173`);
  with `overwrite` the existing variant stays in the copy set (`:178-181`), otherwise it is appended
  to `skipped` and dropped (`:182-191`).
* **`--dry-run`** — `dest_variant = None`, no payload copy, no `pre_variant_install`, no
  `install_variant` (`:204-205`).
* **`--keep-timestamp`** — if false **and** no explicit `timestamp` override, a fresh
  `int(time.time())` is injected (`:236-237`), i.e. a new timestamp by default. No effect when
  copying into an existing package (`:96-98`).
* **Payload** — `_copy_variant_payload(...)` (`:256-261`), preceded by
  `dest_pkg_repo.pre_variant_install(...)` (`:213`) and, for the first variant only,
  `_copy_package_include_modules(...)` (`:216-221`). `shallow` symlinks each variant's root instead
  of copying (`:81-82`).
* **`--force`** bypasses only the relocatability check (`:89-91`, `:118`).
* `dest_name`/`dest_version` are injected as `overrides["name"]`/`overrides["version"]`
  (`:156-161`).

**`move_package`** — `src/rez/package_move.py:13-14`:

```python
def move_package(package, dest_repository, keep_timestamp: bool = False,
                 force: bool = False, verbose: bool = False):
```

`mv` is **copy + hide, not copy + delete** — "Moving a package means copying the package to a
destination repo, and **ignoring (ie hiding - not removing)** the source package"
(`src/rez/package_move.py:17-19`). Sequence (`:56-85`): (1) `dest_pkg_repo.ignore_package(...,
allow_missing=True)` pre-hides a not-yet-existing dest package (`:65-66`); (2) `copy_package(...)` in
a `try` (`:69-77`); (3) `dest_pkg_repo.unignore_package(...)` in `finally` (`:78-81`); (4)
`package.repository.ignore_package(...)` hides the source (`:84`). It pre-checks that the package does
not already exist at the destination and raises `PackageMoveError` if it does (`:48-54`) — so `mv`
has no `--overwrite`. **There is no `dry_run` parameter on `move_package`**
(`src/rez/package_move.py:13-14`) and no `--dry-run` on `rez mv` (`src/rez/cli/mv.py:11-31`) —
ABSENT.

**`package_remove`** — `src/rez/package_remove.py`:

```python
def remove_package_family(name: str, path: str, force: bool = False) -> bool:   # :13
def remove_package(name: str, version: Version | str, path: str) -> bool:       # :31
def remove_packages_ignored_since(days: int, paths=None, dry_run=False,
                                  verbose=False) -> int:                        # :53-54
```

All resolve the repo via `package_repository_manager.get_repository(path)` then delegate to the
repository plugin (`:27-28`, `:49-50`, `:70-80`). `remove_package` coerces a `str` version (`:46-47`).
`remove_packages_ignored_since` iterates `paths or config.packages_path` (`:70`) and sums
`repo.remove_ignored_since(...)` (`:76-80`). The API-level `dry_run` exists **only** on
`remove_packages_ignored_since` (`:54`) — which is exactly why the CLI rejects `--dry-run` with
`-p`/`-f`. `force` on `remove_package_family` (`:13`) is what `--force-family` maps to
(`src/rez/cli/rm.py:75`).

## 22. Caching

Rez 3.4.0 has **three distinct caching layers**: memcached (cross-process), the in-process resource
pool (LRU), and the on-disk package cache.

### 22.1 memcached

Config: `"memcached_uri": OptionalStrList` — `src/rez/config.py:425`; `OptionalStrList` =
`Or(And(None, Use(lambda x: [])), [str])` (`:218-219`). Default `memcached_uri = []`
(`src/rez/rezconfig.py:170`), documented `src/rez/rezconfig.py:167-169`.

Master switches and thresholds:

| Setting | `config.py` | `rezconfig.py` |
|---|---|---|
| `resolve_caching` | `:493` | `:150` |
| `cache_package_files` | `:494` | `:155` |
| `cache_listdir` | `:495` | `:160` |
| `resource_caching_maxsize` | `:474` | `:165` |
| `memcached_package_file_min_compress_len` | `:477` | — |
| `memcached_context_file_min_compress_len` | `:478` | — |
| `memcached_listdir_min_compress_len` | `:479` | — |
| `memcached_resolve_min_compress_len` | `:480` | — |

`rez memcache` CLI — `src/rez/cli/memcache.py`, entry point `rez-memcache`
(`src/rez/cli/_entry_points.py:176`). Flags: `--flush` (`:12-14`), `--stats` (`:15-17`),
`--reset-stats` (`:18-20`), `--poll` (`:21-23`), `--interval SECS` (float, default `1.0`)
(`:24-26`), `--warm` (`:27-29`). Client constructed as
`Client(servers=config.memcached_uri, debug=config.debug_memcache)` (`:87-88`); hard-exits with
"memcaching is not enabled." if falsy (`:90-92`), relying on `Client.__bool__`
(`src/rez/utils/memcached.py:57-58`). `--warm` touches `package.data` across
`config.nonlocal_packages_path` (`:103-121`).

`src/rez/utils/memcached.py`:

| Symbol | Line | Role |
|---|---|---|
| `Client` | `:26` | Wrapper over `memcache.Client` adding unlimited key length and caching of `None` (`:27-33`). |
| `Client._Miss` / `miss` | `:34-38` | Falsy sentinel distinguishing "cached None" from "miss". |
| `Client.__init__(servers, debug=False)` | `:42` | |
| `Client.set` / `.get` / `.delete` / `.flush` | `:86` / `:101` / `:125` / `:132` | |
| `Client.get_stats` / `.reset_stats` / `.test_servers` | `:152` / `:160` / `:71` | |
| `_ScopedInstanceManager` | `:201` | Thread-local refcounted client sharing. |
| `memcached_client(...)` | `:230-231` | `@contextmanager` sharing one client across nested `with` blocks. |
| `pool_memcached_connections(func)` | `:253` | Decorator wrapping a function in `memcached_client()`. |
| `memcached(servers, key=None, from_cache=None, to_cache=None, time=0, min_compress_len=0, debug=False)` | `:272-273` | The memoization decorator; degenerates to a pass-through when `servers` is falsy (`:383-388`). |
| `memcached.default_key` | `:324-349` | Key = `repr((module[.cls].funcname, nargs, sorted(kwargs)))`. |
| `DoNotCache(result)` | `:407-409` | Wrap a return value to suppress caching. |

Applied in the filesystem repository: `_get_family_dirs` / `_get_version_dirs` are wrapped with
`memcached(servers=... if config.cache_listdir else None, ...)` and `iter_package_families` /
`iter_packages` with `pool_memcached_connections` —
`src/rezplugins/package_repository/filesystem.py:542-557`, `:569`, `:574`. Per-repository opt-out via
a `settings.yaml` `disable_memcache` key (`:512-521`).

### 22.2 `cache_packages_path`

Config: `"cache_packages_path": OptionalStr` — `src/rez/config.py:438` (`OptionalStr` =
`Or(None, str)`, `:182-183`); default `None` (`src/rez/rezconfig.py:268`), documented
`src/rez/rezconfig.py:266-267` ("If this is None, then package caching is disabled"). Related:
`default_cachable` (`src/rez/config.py:407`), `default_cachable_per_package` (`:405`),
`default_cachable_per_repository` (`:406`), `read_package_cache` (`:531`),
`write_package_cache` (`:532`).

### 22.3 `src/rez/utils/resources.py`

| Symbol | Line | Role |
|---|---|---|
| `Resource` | `:56` | `metaclass=LazyAttributeMeta`; lazy validation + lazy data load. |
| `Resource.normalize_variables` | `:96-97` | Handle canonicalisation hook. |
| `Resource.handle` / `._data` | `:105-106` / `:110-111` | `cached_property`s; `_data` is the lazily loaded payload. |
| `Resource._load()` | `:136` | Subclass hook. |
| `ResourceHandle` | `:152` | Hashable identity; `to_dict` (`:166`) / `from_dict` (`:172-173`). |
| `ResourcePool` | `:204` | The cache. |
| `ResourcePool.__init__(cache_size=None)` | `:212-215` | `cache = lru_cache(maxsize=cache_size); self.cached_get_resource = cache(self._get_resource)`. |
| `ResourcePool.register_resource` | `:217-233` | Keyed on `resource_class.key`. |
| `ResourcePool.clear_caches()` | `:238-239` | |
| `ResourcePool._get_resource(handle)` | `:248-250` | Instantiates on miss. |
| `ResourceWrapper` | `:253` | `metaclass=AttributeForwardMeta`; subclasses set `keys` (`:271`). |

Wiring: `PackageRepositoryManager.__init__` creates the pool with
`config.resource_caching_maxsize` (`-1` → `None`) — `src/rez/package_repository.py:539-544`.

**`load_resource`, `CachedFile`, `serialised_payload` and in-file `memcached` decorators are all
ABSENT** from `src/rez/utils/resources.py`. Searched: full read (309 lines);
`grep -rn "load_resource\|CachedFile\|serialised_payload" src/` excluding `vendor/` → zero hits. The
`memcached` decorator lives in `src/rez/utils/memcached.py:272`. `cached_property` is imported from
`rez.utils.data_utils` (`src/rez/utils/resources.py:40-41`) and defined at
`src/rez/utils/data_utils.py:223` (`cached_class_property` at `:269`).

### 22.4 `src/rez/package_cache.py` and `rez pkg-cache`

`PackageCache` (`src/rez/package_cache.py:39`) is explicitly **not** a package repository: "A package
cache is **not** a package repository. It just stores copies of variant payloads - no package
definitions are stored" (`:53-54`). Layout: `/<cache_dir>/foo/1.0.0/af8d/a/<payload>` where `af8d` is
the first 4 chars of the SHA-1 of the variant handle (`:56-67`, hashed at `:1041`, path built at
`:1000`).

Status constants (`:70-77`): `VARIANT_NOT_FOUND=0`, `VARIANT_FOUND=1`, `VARIANT_CREATED=2`,
`VARIANT_COPYING=3`, `VARIANT_COPY_STALLED=4`, `VARIANT_PENDING=5`, `VARIANT_REMOVED=6`,
`VARIANT_SKIPPED=7`, with `STATUS_DESCRIPTIONS` at `:79-90`.

Key API: `__init__(path)` (`:96`), `get_cached_root(variant)` (`:112`),
`add_variant(variant, force=False, wait_for_copying=False)` (`:213`), `remove_variant` (`:423`),
`add_variants_async` (`:489`), `add_variants` (`:500`), `get_variants` (`:630`), `run_daemon` (`:700`),
`clean` (`:754`).

CLI `rez pkg-cache` — `src/rez/cli/pkg-cache.py`, entry point `rez-pkg-cache`
(`src/rez/cli/_entry_points.py:190`): `-a/--add-variants` (`:26-29`), `--logs` (`:30-33`),
`-r/--remove-variants` (`:34-37`), `--clean` (`:38-41`), `--daemon` (hidden, `:42-45`) in a mutually
exclusive group (`:24`); plus `--pkg-cache-mode {sync,async}` (`:46-53`), `-c/--columns`
(`:16-22`, `:54-58`), `-f/--force` (`:59-63`), optional `DIR` (`:64-68`, falling back to
`config.cache_packages_path` at `:158-163`). Package-cache config keys:
`src/rez/config.py:482-491`.

---

