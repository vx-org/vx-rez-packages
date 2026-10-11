# Rez 3.4.0 — Authoritative Upstream Specification Baseline

**Purpose.** Normative reference of what upstream Rez *specifies*, so that other auditors can
compare a re-specification (e.g. `rez-next`) against it dimension by dimension.

**Source of truth.** A read-only shallow clone of upstream Rez
(`AcademySoftwareFoundation/rez`, branch `main`) at commit `f622b81`, version confirmed at
`src/rez/utils/_version.py:6` (`_rez_version = "3.4.0"`). The clone was a scratch working copy
and is not part of this repository.

**Citation discipline.** Every claim below carries a `src/...:LINE` (or `docs/...:LINE`) reference
to a file that was opened and read at that line. Where a concept is genuinely *not* in Rez, the
entry says `ABSENT — searched: <paths/patterns>` and records the search that was run. Nothing here
is inferred from memory or from a path that was not opened.

**Reading conventions used in this document**

* `src/...` paths are relative to the clone root; `docs/...` likewise.
* "Contract" means: the abstract base class, the methods a plugin must implement, and the
  mechanism by which Rez finds the plugin.
* `NotImplementedError` bodies are Rez's usual way of expressing "abstract" — **`src/rez/build_system.py`,
  `src/rez/package_repository.py`, `src/rez/release_vcs.py` and `src/rez/release_hook.py` do not use
  `abc.ABCMeta` / `@abstractmethod`**; they raise `NotImplementedError`. (By contrast
  `src/rez/package_resources.py:381`, `:385`, `:409`, `:414` *does* use `@abstractmethod`.)

**Global extension-point summary** (detail in §A.1): Rez 3.4.0 registers exactly **seven** plugin
types, at `src/rez/plugin_managers.py:543-549`: `shell`, `release_vcs`, `release_hook`,
`build_system`, `package_repository`, `build_process`, `command`.

---

# A. Build

## 1. `build_system` plugin family

### 1.1 Enumeration

Plugin namespace package: `src/rezplugins/build_system/__init__.py` (namespace extension, see §1.4).

| Plugin | Module | Class | What it does |
|---|---|---|---|
| `cmake` | `src/rezplugins/build_system/cmake.py` | `CMakeBuildSystem` (`:32`) | Runs `cmake` to generate build files, then the chosen child generator (`make` / `nmake` / `ninja` / `mingw32-make`), then `<generator> install` if installing. |
| `custom` | `src/rezplugins/build_system/custom.py` | `CustomBuildSystem` (`:33`) | Executes the `build_command` declared in `package.py` (a `str` or `list[str]`) inside the resolved build environment. This is Rez's generic escape hatch. |
| `make` | `src/rezplugins/build_system/make.py` | `MakeBuildSystem` (`:12`) | **STUB — cannot build anything.** Exists only so a `Makefile` is *detected*, which lets `make` be suppressed as `cmake`'s child build system. Its `__init__` unconditionally raises `NotImplementedError`. |

Non-plugin members of the directory:

* `src/rezplugins/build_system/rezconfig.py` (`:8-35`) — plugin defaults for the `cmake` plugin
  (`build_system`, `build_target`, `cmake_args`, `cmake_binary`, `make_binary`, `install_pyc`),
  auto-loaded per §1.4. Note `:34-35`: on non-POSIX, `build_system` is forced to `"nmake"`.
* `cmake_files/`, `template_files/` — CMake module/template assets shipped with the plugin.

The `make` stub is a factual finding worth flagging to any re-specification:

```python
# src/rezplugins/build_system/make.py:21-24
def __init__(self, working_dir, opts=None, package=None, write_build_scripts: bool = False,
             verbose: bool = False, build_args=[], child_build_args=[]) -> None:
    super(MakeBuildSystem, self).__init__(working_dir)
    raise NotImplementedError
```

Enumerate plugin names at runtime: `get_buildsys_types()` — `src/rez/build_system.py:31-34`
(delegates to `plugin_manager.get_plugins('build_system')`).

### 1.2 The plugin contract

Base class `BuildSystem` — `src/rez/build_system.py:126`.

| Member | Signature / kind | Line | Required? |
|---|---|---|---|
| `name()` | `@classmethod -> str` | `:129-132` | Yes (`raise NotImplementedError`) |
| `__init__` | `(working_dir, opts=None, package=None, write_build_scripts=False, verbose=False, build_args=[], child_build_args=[])` | `:134-171` | Inherited normally |
| `is_valid_root` | `@classmethod (path, package=None) -> bool` | `:173-176` | Yes |
| `child_build_system` | `@classmethod -> str \| None` | `:178-191` | No (default `None`, `:191`) |
| `bind_cli` | `@classmethod (parser, group) -> None` | `:193-203` | No (default `pass`, `:203`) |
| `build` | `(context, variant, build_path, install_path, install=False, build_type=BuildType.local) -> BuildResult` | `:205-239` | **Yes — the core method** |
| `set_standard_vars` | `@classmethod (executor, context, variant, build_type, install, build_path, install_path=None)` | `:241-303` | Inherited (sets all build env vars, §A.3) |
| `add_pre_build_commands` | `@classmethod (executor, variant, build_type, install, build_path, install_path=None)` | `:305-340` | Inherited (§A.2) |
| `add_standard_build_actions` | `@classmethod (executor, context, variant, build_type, install, build_path, install_path=None)` | `:342-358` | Inherited; currently only calls `set_standard_vars` (`:350-358`) |

`build()` **must** return a `BuildResult`, a `TypedDict` declared at `src/rez/build_system.py:25-28`:

```python
class BuildResult(TypedDict, total=False):
    success: bool
    extra_files: list[str]
    build_env_script: str
```

Semantics (documented at `src/rez/build_system.py:226-238`):

* `success` — falsy means the build failed. The caller deletes a partially installed payload and
  raises `BuildError` (`src/rezplugins/build_process/local.py:276-281`).
* `extra_files` — files of interest (not build targets), located under `build_path`; Rez copies them
  into the variant install dir (`src/rezplugins/build_process/local.py:292-298`). `build.rxt` is
  always added (`local.py:245`, `:297-298`).
* `build_env_script` — only when the build system was constructed with `write_build_scripts=True`
  (`src/rez/build_system.py:150-153`); a script that drops the user into the build environment.

`build()` is invoked once per variant at `src/rezplugins/build_process/local.py:268-274`.

Constructor side effects worth noting: `src/rez/build_system.py:159-162` raises `BuildSystemError`
if `is_valid_root(working_dir)` is false, and `:164` defaults `self.package` to the developer
package in `working_dir`.

### 1.3 How a plugin is selected from `package.py`

`get_valid_build_systems(working_dir, package=None)` — `src/rez/build_system.py:37-86`.

```python
# src/rez/build_system.py:61-70
if package:
    if getattr(package, "build_command", None) is not None:
        buildsys_name: str | None = "custom"
    else:
        buildsys_name = getattr(package, "build_system", None)

    # package explicitly specifies build system
    if buildsys_name:
        cls = plugin_manager.get_plugin_class('build_system', buildsys_name)
        return [cls]
```

**Ordering rule (normative):** `build_command` **takes precedence over** `build_system`. If a
package defines a `build_command`, Rez forces the `custom` build system and never consults
`build_system` (`src/rez/build_system.py:62-65`). This is also why `CustomBuildSystem.is_valid_root`
tests for `build_command` (`src/rezplugins/build_system/custom.py:61-69`).

If neither attribute is set, Rez falls back to **detection** (`src/rez/build_system.py:72-86`): every
registered plugin's `is_valid_root()` is tried, then child build systems are subtracted
(`:83-84`) so that a directory containing both `CMakeLists.txt` and a generated `Makefile` resolves
to `cmake`, not `make`.

`create_build_system(...)` — `src/rez/build_system.py:89-123` — errors if zero build systems match
(`:103-105`) or if more than one remains ambiguous (`:107-110`).

The CLI override is `-b/--build-system`, whose `choices` are computed at parser-build time from
`get_valid_build_systems(os.getcwd(), package=package)` — `src/rez/cli/build.py:54-71`.

### 1.4 Where third-party plugins register

Two mechanisms, both implemented in `src/rez/plugin_managers.py` and both run for every plugin type
(`load_plugins`, `:132-134`):

1. **Namespace-package discovery** — `load_plugins_from_namespace()`, `:136-191`.
   A plugin type `T` maps to the importable package `rezplugins.T` (`:139-140`). That package's
   `__path__` is extended via `extend_path` (`:44`, `:49-50`) — see the in-tree example
   `src/rezplugins/command/__init__.py:5-6` — so a third-party distribution that ships a *sparse*
   `rezplugins/` tree merges into Rez's. Search paths are **reversed** so custom plugins are found
   before builtins (`:150-152`). Modules starting with `_` and the module named `rezconfig` are
   skipped (`:165-166`). Each module must expose `register_plugin()` returning the class
   (`:234-247`, `:244-247`).
2. **Setuptools entry points** — `load_plugins_from_entry_points()`, `:193-214`.
   The entry-point group is `rez.plugins.<type>` (`:194`), e.g. `rez.plugins.build_system`
   (`:516-519` for the type name). Loaded via `importlib.metadata.entry_points` (`:24-26`,
   `:198-201`).

Additional rules:

* A `rezconfig` file **next to the plugin module** is auto-loaded as plugin defaults —
  `load_config_from_plugin`, `:229-232`.
* Plugins are registered keyed by module name; a same-named plugin already loaded wins
  (`:168-176`).
* Failed imports are recorded, not fatal — `print_log_plugins_error`, `:216-227`.
* The authoritative prose instructions are the `RezPluginManager` docstring,
  `src/rez/plugin_managers.py:300-352` (create `rezplugins/<type>/<name>.py`, subclass the base,
  add `register_plugin()`, and point `plugin_path` at the directory **above** `rezplugins/`
  — `:341-351`).
* Worked example in-tree: `example_extensions/hello_cmd/` — a `command` plugin at
  `example_extensions/hello_cmd/rezplugins/command/world.py:33-41` (`WorldCommand` +
  `register_plugin()`), packaged by `example_extensions/hello_cmd/setup.py:8-15`, with usage
  instructions in `example_extensions/hello_cmd/README.md:1-12`.

Plugin type registration (the complete set in 3.4.0) — `src/rez/plugin_managers.py:543-549`:

| Type name | Type class | Line |
|---|---|---|
| `shell` | `ShellPluginType` | `:498` / `type_name` `:501` |
| `release_vcs` | `ReleaseVCSPluginType` | `:504` / `:507` |
| `release_hook` | `ReleaseHookPluginType` | `:510` / `:513` |
| `build_system` | `BuildSystemPluginType` | `:516` / `:519` |
| `package_repository` | `PackageRepositoryPluginType` | `:522` / `:525` |
| `build_process` | `BuildProcessPluginType` | `:528` / `:531` |
| `command` | `CommandPluginType` | `:534` / `:537` |

### 1.5 How `build_system` interacts with `build_command`

`build_command` is a package attribute, not a build-system attribute. Declared at
`src/rez/package_maker.py:88`:

```python
# src/rez/package_maker.py:86-89
# attributes specific to pre-built packages
Optional("build_system"):           str,
Optional("build_command"):          Or([str], str, False),
```

Note the comment at `src/rez/package_maker.py:86` — upstream itself describes `build_system` /
`build_command` as *"attributes specific to pre-built packages"* (relevant to §F.25).

Accepted shapes: a `str` (shell command line), a `list[str]` (argv, executed without a shell), or
`False` (explicitly "no build") — `src/rez/package_maker.py:88`,
`src/rezplugins/build_system/custom.py:141-172`, `:144-146`.

`CustomBuildSystem.build()` expands these placeholders into the command
(`src/rezplugins/build_system/custom.py:148-161`): `build_path`, `install_path`, `root`,
`install` (the literal string `"install"` when installing, else `''`), `name`, `variant_index`
(`''` when the package has no variants), `version`.

`--ba/--build-args` are appended: quoted onto a `str` command (`:164-165`) or concatenated onto a
`list` command (`:170`).

`build_system` / `build_command` / `preprocess` / `pre_build_commands` / `requires_rez_version` are
**stripped on install** — they never reach an installed package definition:
`package_build_only_keys`, `src/rez/package_resources.py:42-48`, applied at
`src/rezplugins/package_repository/filesystem.py:1289-1291`, `:1300`, `:1309`.

---

## 2. `build_command` / `pre_build_commands` / `post_build_commands`

### 2.1 Definitions

| Attribute | Declared at | Type |
|---|---|---|
| `build_command` | `src/rez/package_maker.py:88` | `Or([str], str, False)` |
| `pre_build_commands` | `src/rez/package_resources.py:160` | `SourceCode` (schema form) |
| `pre_build_commands` | `src/rez/package_maker.py:83` | `_commands_schema` (POD form) |
| `pre_build_commands` | `src/rez/package_serialise.py:99` | `source_code_schema` (serialised form) |
| `post_build_commands` | **ABSENT** | see below |

`_commands_schema` (`src/rez/package_resources.py:206-209`) accepts `SourceCode`, a `callable`,
a `str` code block, or a rez-1 style `list[str]`.

`pre_build_commands` is in `package_rex_keys` (`src/rez/package_resources.py:51-57`), i.e. it is
interpreted by **rex**, not plain Python.

### 2.2 `post_build_commands` is not part of Rez

`ABSENT — searched: grep -rn "pre_build_commands\|post_build_commands" src/ --include=*.py`
(whole tree). The only `post_build_commands`-shaped hits anywhere are in a *release hook plugin's*
settings schema — `src/rezplugins/release_hook/command.py:46`, `:100`, and
`src/rezplugins/release_hook/rezconfig.py:94`, `:99`, `:101`, `:104` — which is a `command` release
hook's own `pre_build_commands` / `post_build_commands` option pair, **not** a package attribute and
**not** invoked by the build process. A re-specification that adds `post_build_commands` is adding a
new concept, not porting one.

### 2.3 `pre_build_commands` execution timing

Executed by `BuildSystem.add_pre_build_commands` — `src/rez/build_system.py:305-340`:

```python
# src/rez/build_system.py:325-340
pre_build_commands = getattr(variant, "pre_build_commands")
...
if pre_build_commands:
    with executor.reset_globals():
        executor.bind("this", bound_variant)
        executor.bind("build", ROA(build_ns))
        executor.execute_code(pre_build_commands)
```

Namespace bound into the rex code (`:313-318`):

* `this` — the variant wrapped in a `VariantBinding` (`:331-334`), so `this.root` is path-normalised.
* `build` — a read-only object with `build_type` (`"local"` or `"central"`), `install` (bool),
  `build_path`, `install_path` (`:313-318`, wrapped by `RO_AttrDictWrapper` at `:310`, `:339`).

**Timing.** Both shipped build systems pass `add_pre_build_commands` as the
`post_actions_callback` of `context.execute_shell(...)`
(`src/rezplugins/build_system/cmake.py:168-175`, `:183`;
`src/rezplugins/build_system/custom.py:179-186`, `:233`).
`execute_shell` runs, in order
(`src/rez/resolved_context.py:1541-1552`):

1. `actions_callback` → emits `"pre-actions-callback"` (`:1541-1543`); this is where
   `set_standard_vars` puts the `REZ_BUILD_*` environment variables.
2. `self._execute(executor)` → the resolved context's own commands (`:1545`).
3. `post_actions_callback` → emits `"post-actions-callback"` (`:1550-1552`) — **this is where
   `pre_build_commands` is emitted.**

The generated context file is written at `:1562-1563` and only *then* is the shell spawned
(`:1568-1569`). So the name is accurate from the user's point of view: **`pre_build_commands` runs
before the build command**, because it is appended to the environment script that the build command
is later run inside. It is "post" only relative to context resolution.

**Consequence for `cmake`:** the same `post_actions_callback` is passed to **all three**
`execute_shell` calls — configure (`src/rezplugins/build_system/cmake.py:178-184`), build
(`:230-236`) and install (`:243-249`) — so a `cmake` package's `pre_build_commands` is emitted into
each of the three generated context scripts.

---

## 3. Build-time environment variables

All build environment variables are set in exactly one place:
`BuildSystem.set_standard_vars()` — `src/rez/build_system.py:241-303`, table at `:263-303`.

| Variable | Line | Value / semantics |
|---|---|---|
| `REZ_BUILD_ENV` | `:264` | Always literal `"1"` in a build env. |
| `REZ_BUILD_PATH` | `:265` | Build output dir, path-normalised. |
| `REZ_BUILD_THREAD_COUNT` | `:266` | `str(package.config.build_thread_count)`. |
| `REZ_BUILD_VARIANT_INDEX` | `:267` | `str(variant.index or 0)`. |
| `REZ_BUILD_VARIANT_REQUIRES` | `:268` | Space-joined `variant.variant_requires` (built at `:250`). |
| `REZ_BUILD_VARIANT_SUBPATH` | `:269` | `variant._non_shortlinked_subpath`, or `''` when `variant.index is None` (`:252-255`). |
| `REZ_BUILD_PROJECT_VERSION` | `:270` | `str(package.version)`. |
| `REZ_BUILD_PROJECT_NAME` | `:271` | `package.name`. |
| `REZ_BUILD_PROJECT_DESCRIPTION` | `:272` | `package.description`, stripped. |
| `REZ_BUILD_PROJECT_FILE` | `:273` | `package.filepath`. |
| `REZ_BUILD_SOURCE_PATH` | `:274-278` | `os.path.dirname(package.filepath)` — the dir containing `package.py`. |
| `REZ_BUILD_REQUIRES` | `:279-283` | Space-joined `context.requested_packages(True)` — i.e. the resolved build request. |
| `REZ_BUILD_REQUIRES_UNVERSIONED` | `:284-288` | Same list, names only. |
| `REZ_BUILD_TYPE` | `:289` | `build_type.name` — see below. |
| `REZ_BUILD_INSTALL` | `:290` | `"1"` if installing, else `"0"`. |
| `REZ_BUILD_INSTALL_PATH` | `:293-294` | **Conditional** — only set when `install_path` is truthy. |
| `REZ_IN_REZ_RELEASE` | `:296-299` | **Conditional** — rez-1 compatibility only; requires `config.rez_1_environment_variables`, not `config.disable_rez_1_compatibility`, and `build_type == BuildType.central`. |

Assignment loop: `src/rez/build_system.py:301-303`. Every value is wrapped in `rez.rex.literal`
(imported `:12`) to prevent shell injection — the security comment is at `:257-262`.

**`REZ_BUILD_TYPE` values.** The enum is `BuildType` — `src/rez/build_process.py:77-80`:

```python
class BuildType(Enum):
    """ Enum to represent the type of build."""
    local = 0
    central = 1
```

* `local` — a build/install into the local (developer) packages path, i.e. `rez build --install`.
  Set explicitly at `src/rezplugins/build_process/local.py:361`.
* `central` — a release into the release packages path. Set explicitly at
  `src/rezplugins/build_process/local.py:416`.

Documented at `docs/source/environment.rst:189-191`: *"One of `local` or `central`. Value is
`central` if a release is occurring."*

**Code vs. docs.** `docs/source/environment.rst:135-204` documents these variables as a Sphinx
`glossary`. It is complete for the unconditional set — `REZ_BUILD_ENV`:137, `REZ_BUILD_INSTALL`:141,
`REZ_BUILD_INSTALL_PATH`:145, `REZ_BUILD_PATH`:149, `REZ_BUILD_PROJECT_DESCRIPTION`:153,
`REZ_BUILD_PROJECT_FILE`:157, `REZ_BUILD_PROJECT_NAME`:161, `REZ_BUILD_PROJECT_VERSION`:165,
`REZ_BUILD_REQUIRES`:169, `REZ_BUILD_REQUIRES_UNVERSIONED`:174, `REZ_BUILD_SOURCE_PATH`:178,
`REZ_BUILD_THREAD_COUNT`:182, `REZ_BUILD_TYPE`:189, `REZ_BUILD_VARIANT_INDEX`:193,
`REZ_BUILD_VARIANT_REQUIRES`:197, `REZ_BUILD_VARIANT_SUBPATH`:202 — plus `__PARSE_ARG_XXX`:206.
The **only** variable in the code table with no doc entry is the conditional rez-1 compatibility
variable `REZ_IN_REZ_RELEASE` (`src/rez/build_system.py:296-299`).

The `cmake` plugin additionally passes build state to CMake as `-D` defines:
`-DREZ_BUILD_TYPE=%s` and `-DREZ_BUILD_INSTALL=%d`
(`src/rezplugins/build_system/cmake.py:147-148`).

**Related config:** `build_thread_count` — `src/rez/rezconfig.py:793`, documented
`src/rez/rezconfig.py:785-792` (accepts `"physical_cores"` / `"logical_cores"` / an int).
`build_directory` — `src/rez/rezconfig.py:783`.

**Env-var override mechanism (general):** any config setting `foo_bar` can be overridden by the
environment variable `REZ_FOO_BAR` — `src/rez/config.py:87-89`
(`return "REZ_%s" % self.key.upper()`). That is how `REZ_BUILD_THREAD_COUNT` and
`REZ_RELEASE_PACKAGES_PATH` style overrides work; it does **not** apply to `timestamp`, which is not
a config setting (§A.9).

---

## 4. `variants` / `variant_requires`

### 4.1 Schema

`variants` is declared on the **package** schema only, and deliberately cannot be late-bound:

```python
# src/rez/package_resources.py:178-182
package_schema_dict = package_base_schema_dict.copy()
package_schema_dict.update({
    # deliberately not possible to late bind
    Optional("variants"):               [[PackageRequest]]
})
```

i.e. `list[list[PackageRequest]]`. Equivalent POD entry: `src/rez/package_resources.py:230-231`
(note the identical "deliberately not possible to late bind" comment at `:230`). Serialised form:
`src/rez/package_serialise.py:89`. Maker form: `src/rez/package_maker.py:65-66`, again with the same
comment at `:65`.

`variant_requires` is **not** a package attribute — it is derived. For a `Variant`, `requires` is
the parent package's `requires` plus the variant's own entry:

```python
# src/rez/packages.py:429-431
return (
    (self.parent.requires or []) + self.variant_requires
)
```

`variant.index` is `None` for a package with no variants (`src/rez/packages.py:433-452` region;
iterated at `src/rez/package_resources.py:430-445`).

### 4.2 Variant subpath computation

Canonical location: `VariantResourceHelper._subpath()` — `src/rez/package_resources.py:493-521`.

```python
# src/rez/package_resources.py:493-521
def _subpath(self, ignore_shortlinks: bool = False) -> str | None:
    if self.index is None:
        return None

    if self.parent.hashed_variants:
        vars_str = str(list(map(str, self.variant_requires)))
        h = sha1(vars_str.encode("utf8"))
        hashdir = h.hexdigest()
        ...                      # shortlink lookup, :502-515
        return hashdir
    else:
        dirs = [x.safe_str() for x in self.variant_requires]
        subpath = os.path.join(*dirs)
        return subpath
```

Two conventions:

1. **Default (requirement-path) convention** — one directory per variant requirement, in
   declaration order, joined by `os.path.join` (`:518-521`). Each element is the requirement's
   `safe_str()` (`:519`).
2. **Hashed convention** — enabled per-package by `hashed_variants = True`; the subpath is the
   **SHA-1 hexdigest** of `str(list(map(str, variant_requires)))` (`:497-500`, `:517`).

`hashed_variants` is a package attribute: `src/rez/package_resources.py:147`
(and `:242` POD, `src/rez/package_serialise.py:91`).

**On the `platform-X/arch-Y/os-Z` convention:** there is **no formatting code** that produces that
string shape — it is an emergent consequence of convention (1) plus packages naming themselves
`platform`, `arch`, `os`. `src/rez/utils/formatting.py` contains no variant-subpath logic
(`ABSENT — searched: grep -n "def \|subpath" src/rez/utils/formatting.py`, full outline read; no
`subpath` symbol). The convention is documented, not coded:
`docs/source/variants.rst:106-124`, with the canonical example at `:116-119`:

```python
variants = [
   ["platform-linux", "arch-x86_64", "os-Ubuntu-12.04"],
   ["platform-linux", "arch-x86_64", "os-Ubuntu-16.04"]
]
```

and the resulting disk layout at `docs/source/variants.rst:53-56`
(`/rez/packages/my_maya_plugin/1.0.0/maya-2016.sp2/<PAYLOAD>`).

Accessors:

* `VariantResource.subpath` (public, cached) — `src/rez/package_resources.py:371-379`.
* `VariantResourceHelper._root()` — `:523-529`, `base` + subpath.
* `Variant._non_shortlinked_subpath` — `src/rez/packages.py:486-488`, calls
  `self.resource._subpath(ignore_shortlinks=True)`. This is the variant used for **build and install
  paths** (`src/rez/build_system.py:255`; `src/rezplugins/build_process/local.py:164`).

**Variant shortlinks.** When `hashed_variants` is on and `config.use_variant_shortlinks` is true,
Rez looks for a matching symlink under `<base>/<variant_shortlinks_dirname>` and returns that
instead of the raw hash (`src/rez/package_resources.py:502-515`). Config:
`variant_shortlinks_dirname` — `src/rez/rezconfig.py:816` (default `"_v"`);
`use_variant_shortlinks` — documented at `src/rez/rezconfig.py:818-821`. Shortlinks are created
during install at `src/rezplugins/build_process/local.py:193-218` via
`create_unique_base26_symlink` (`:207-208`); failure is a warning only (`:210-218`).

### 4.3 Variant iteration during build/install

`BuildProcessHelper.visit_variants(func, variants=None, **kwargs)` —
`src/rez/build_process.py:210-239`:

1. If `variants` was given, resolve possibly-negative indices via
   `resolve_variant_indices(variants, self.package.num_variants)` (`:214-216`); raise `BuildError`
   listing invalid indices (`:217-220`); sort the resolved set (`:221`).
2. Iterate `self.package.iter_variants()` (`:227`); skip non-selected variants with a header
   (`:228-232`); else call `func(variant, **kwargs)` (`:235`).
3. Return `(num_visited, results)` (`:239`).

`resolve_variant_indices` — `src/rez/util.py:195-215` — maps negatives modulo `num_variants`
(`:214`); when `num_variants <= 0` the input passes through unchanged with no invalid entries
(`:210-211`). This is what makes `--variants -1` mean "the last variant".

Per-variant work: `LocalBuildProcess._build_variant_base` —
`src/rezplugins/build_process/local.py:149-305`. Paths:

```python
# src/rezplugins/build_process/local.py:157-166
install_path = install_path or self.package.config.local_packages_path
package_install_path = self.get_package_install_path(install_path)
variant_build_path = self.build_path

if variant.index is None:
    variant_install_path = package_install_path
else:
    subpath = variant._non_shortlinked_subpath
    variant_build_path = os.path.join(variant_build_path, subpath)
    variant_install_path = os.path.join(package_install_path, subpath)
```

Note that variant iteration is **sequential** — `local.py:227` — and the local build process
docstring says so (`src/rezplugins/build_process/local.py:43-46`).

---

## 5. `requires` / `build_requires` / `private_build_requires`

### 5.1 Schema

All three are optional and **late-bindable**:

```python
# src/rez/package_resources.py:131-134
# dependencies
Optional('requires'):               late_bound([PackageRequest]),
Optional('build_requires'):         late_bound([PackageRequest]),
Optional('private_build_requires'): late_bound([PackageRequest]),
```

POD equivalents: `src/rez/package_resources.py:226-228`. Serialised:
`src/rez/package_serialise.py:85-87`. Maker: `src/rez/package_maker.py:61-63`.
All four spellings agree, and `build_requires` / `private_build_requires` carry **no** extra
semantics in the schema — they differ only in how `get_requires()` (§A.5.2) and consumers treat them.

`late_bound` = `Or(SourceCode, schema)` (`src/rez/package_resources.py:70-71`); when late-bound,
the value is validated against `late_requires_schema` (`:75-77`).

### 5.2 Semantics

`Variant.get_requires(build_requires=False, private_build_requires=False)` —
`src/rez/packages.py:433-452`:

```python
# src/rez/packages.py:445-452
requires = self.requires or []

if build_requires:
    requires = requires + (self.build_requires or [])
if private_build_requires:
    requires = requires + (self.private_build_requires or [])

return requires
```

`self.requires` for a variant already includes the variant's own requirements
(`src/rez/packages.py:429-431`), so `get_requires()` without flags returns runtime requirements only.

The **build environment** is resolved with all three enabled:

```python
# src/rez/build_process.py:259-260
request = variant.get_requires(build_requires=True,
                               private_build_requires=True)
```

So `build_requires` and `private_build_requires` are present in the build context (and thus in
`REZ_BUILD_REQUIRES`, `src/rez/build_system.py:279-283`) but are *not* part of the installed
package's runtime `requires`.

### 5.3 Are they recorded on the installed package?

**`build_requires` and `private_build_requires` ARE written into the installed package
definition.** The set of attributes stripped at install time is
`package_build_only_keys` — `src/rez/package_resources.py:42-48`:

```python
package_build_only_keys = (
    "requires_rez_version",
    "build_system",
    "build_command",
    "preprocess",
    "pre_build_commands"
)
```

which contains neither. They are therefore carried through into the installed `package.py`
(`_get_package_data` at `src/rezplugins/package_repository/filesystem.py:1274-1287`, written at
`:1450-1451`).

`private_build_requires` is additionally a **searchable** attribute — it is in the search field list
at `src/rez/package_search.py:357` and is honoured by the search API
(`src/rez/package_search.py:34`, `:49-50`, `:86-90`) and by `rez-depends`
(`src/rez/cli/depends.py:67`). Its semantic distinction from `build_requires` is *documentational*:
`private_build_requires` marks build-time tools that should not be considered part of the package's
public dependency surface (see its use in the test fixtures, e.g.
`src/rez/data/tests/builds/packages/foo/1.0.0/package.py:9`).

---

## 6. `rez build` CLI

`src/rez/cli/build.py` (180 lines). Every flag:

### 6.1 Own flags — `setup_parser`, `src/rez/cli/build.py:87-110`

| Flag | Line | Meaning |
|---|---|---|
| `-c`, `--clean` | `:88-90` | Clear the current build before rebuilding. |
| `-i`, `--install` | `:91-94` | Install the build to the local packages path. Use `--prefix` for a custom install path. |
| `-p`, `--prefix PATH` | `:95-97` | Install to a custom package repository path. |
| `--fail-graph` | `:98-101` | If the build environment fails to resolve due to a conflict, display the resolve graph as an image. |
| `-s`, `--scripts` | `:102-106` | Create build scripts rather than performing the full build; running them places you into a build environment. |
| `--view-pre` | `:107-109` | Just view the preprocessed package definition and exit. |

`--view-pre` short-circuits in `command()` at `:142-144`
(`package.print_info(format_=FileFormat.py, skip_attributes=["preprocess"])` then `sys.exit(0)`).
`--fail-graph` is handled at `:169-180`.

### 6.2 Shared flags — `setup_parser_common`, `src/rez/cli/build.py:35-84`
(shared verbatim with `rez release`, which calls it at `src/rez/cli/release.py:42`)

| Flag | Line | Meaning |
|---|---|---|
| `--process TYPE` | `:43-46` | Build process to use; `choices` = `get_build_process_types()`, default `config.default_build_process`. |
| `-b`, `--build-system TYPE` | `:67-71` | Build system to use. If not specified it is detected. Set `build_system` or `build_command` in the package to specify it there. |
| `--variants INDEX [INDEX …]` | `:73-76` | Select variants to build; zero-indexed, negative indices count from the end (`-1` = last variant). |
| `--ba`, `--build-args ARGS` | `:77-80` | Arguments passed to the build system; alternatively list them after a `--`. |
| `--cba`, `--child-build-args ARGS` | `:81-84` | Arguments for the *child* build system, if any; alternatively after a second `--`. |

`--process` choices come from `get_build_process_types()` (`src/rez/build_process.py:36-39`)
= `['local', 'remote']` (see §A.8). Default `config.default_build_process = "local"`
(`src/rez/rezconfig.py:828`), whose docstring explicitly says *"Only 'local' build process is
currently available"* (`src/rez/rezconfig.py:824-825`).

`--variants` is threaded to `builder.build(variants=opts.variants)` at `:168`, and index resolution
is `resolve_variant_indices` (§A.4).

### 6.3 Flags that do **not** exist on `rez build`

| Flag asked about | Status | Evidence |
|---|---|---|
| `--release` | **ABSENT** | Releasing is a separate command, `rez release` (`src/rez/cli/release.py:15-42`). `src/rez/cli/build.py` was read in full (180 lines). |
| `--paths` | **ABSENT** | Not in `src/rez/cli/build.py`. `--paths` exists only on `rez test` (`src/rez/cli/test.py:30-31`) and `rez cp` (`src/rez/cli/cp.py:17-19`). |
| `--keep-tmp` | **ABSENT** | `grep -rn "keep.tmp\|keep_tmp" src/` → only `src/rez/cli/selftest.py:44` (`--keep-tmpdirs`) and `:87`. |
| `--extra-packages` | **ABSENT** | `grep -rn "extra_packages\|extra-packages" src/` → only `src/rez/cli/test.py:27`, `:54`, `:57`, `:79` and `src/rez/package_test.py`. |
| `--view-post` | **ABSENT** | `grep -rn "view_post\|view-post\|view_pre\|view-pre" src/rez/cli/*.py` → only `src/rez/cli/build.py:108` (`--view-pre`) and `:142`. |

`command()` flow: `src/rez/cli/build.py:131-180` — load developer package (`:139-140`), handle
`--view-pre`, resolve build args (`:147`), create build system (`:149-156`), create build process
(`:159-162`), `builder.build(install_path=opts.prefix, clean=opts.clean, install=opts.install,
variants=opts.variants)` (`:165-168`).

---

## 7. Build process model

### 7.1 `BuildStep` does not exist

`ABSENT — searched: grep -rn "BuildStep" src/ docs/` (zero hits anywhere in the clone, code or
docs). Rez 3.4.0 has **no** `BuildStep` enum or step objects. The sequence below is reconstructed
from the actual control flow.

### 7.2 `BuildProcess` contract

`BuildProcess` — `src/rez/build_process.py:83-196`. Abstract-by-`NotImplementedError`:
`name()` `:93-95`; **`build(install_path=None, clean=False, install=False, variants=None) -> int`**
`:147-169`; **`release(release_message=None, variants=None) -> int`** `:171-188`;
`get_changelog()` `:190-196`.

`BuildProcessHelper` — `src/rez/build_process.py:199` — adds the shared machinery
(`visit_variants` `:210-239`, `create_build_context` `:256-299`, `pre_release` `:301-347`,
`post_release` `:349-357`, `run_hooks` `:369-388`, `get_release_data` `:414-448`).

Construction: `create_build_process(process_type, working_dir, build_system, package=None, vcs=None,
ensure_latest=True, skip_repo_errors=False, ignore_existing_tag=False, verbose=False, quiet=False)`
— `src/rez/build_process.py:42-74`. Note `:56-57`: `working_dir` and `package` are **deprecated**
(slated for removal in rez 3.0.0, per the docstring warning) and are ignored by the plugin
constructor (`:66-68`).

### 7.3 Actual per-variant step order (build/install)

`LocalBuildProcess.build()` (`src/rezplugins/build_process/local.py:60-88`) →
`visit_variants(self._build_variant, ...)` (`:68-73`) →
`_build_variant` (`:340-392`) → `_build_variant_base` (`:149-305`) → `build_system.build()`.

| # | Step | Line |
|---|---|---|
| 1 | Resolve package/version install path (`get_package_install_path`) | `local.py:158` |
| 2 | Compute variant build path and variant install path from the subpath | `local.py:159-166` |
| 3 | If `clean`, remove the variant build dir | `local.py:169-170` |
| 4 | Create the build dir | `local.py:172` |
| 5 | If installing: `pkg_repo.pre_variant_install(variant.resource)` | `local.py:186-189` |
| 6 | If installing: create the variant install dir | `local.py:191` |
| 7 | If installing and `hashed_variants`: create the variant shortlink | `local.py:193-218` |
| 8 | **Re-evaluate** the variant with `building=True`, `build_variant_index`, `build_variant_requires` | `local.py:229-234` |
| 9 | **Resolve the build context** and save `build.rxt` (`create_build_context`) | `local.py:237-240`; `src/rez/build_process.py:256-299` |
| 10 | If varianted: write `variant.json` (debug aid for hashed variants) | `local.py:247-262` |
| 11 | **`build_system.build(...)`** — configure → build → install | `local.py:264-274` |
| 12 | On failure: `rmtree` the partial payload; raise `BuildError` | `local.py:276-281` |
| 13 | If installing: copy extra files (`build.rxt`, `variant.json`, `extra_files`) | `local.py:283-298` |
| 14 | If installing: install `@include` modules | `local.py:300-303`; `:307-332` |
| 15 | Back in `_build_variant`: run `pre_install` tests | `local.py:372-379` |
| 16 | If installing: `variant.install(install_path)` — updates the target `package.py` | `local.py:390` |

Note step 8: the re-evaluated variant is used **only** to build the context; the variant actually
installed is the one evaluated with `building` false — `src/rezplugins/build_process/local.py:220-228`.

Step 11's internal stages for `cmake` (`src/rezplugins/build_system/cmake.py`):

* **configure** — `cmake` invocation, `:136-149` (adds `-DCMAKE_INSTALL_PREFIX`, `-DCMAKE_MODULE_PATH`,
  `-DCMAKE_BUILD_TYPE`, `-DREZ_BUILD_TYPE`, `-DREZ_BUILD_INSTALL`, `-G <generator>`), run at `:178-184`.
* **build** — generator invocation with `-j<build_thread_count>` (unless the generator is `nmake`,
  or the user supplied their own `-j`), `:207-236`.
* **install** — the same command with `install` appended, `:238-249`.

For `custom`, step 11 is a single `build_command` execution
(`src/rezplugins/build_system/custom.py:228-234`).

There is no `post_build` step (§A.2).

---

## 8. Remote build

`--process=remote` is **registered but non-functional** in 3.4.0. The entire plugin:

```python
# src/rezplugins/build_process/remote.py:11-24
class RemoteBuildProcess(BuildProcessHelper):
    """The default build process.

    This process builds a package's variants sequentially, on remote hosts.
    """
    @classmethod
    def name(cls) -> str:
        return "remote"

    def build(self, install_path=None, clean: bool = False, install: bool = False, variants=None):
        raise NotImplementedError("coming soon...")

    def release(self, release_message=None, variants=None):
        raise NotImplementedError("coming soon...")
```

* `src/rezplugins/build_process/remote.py:21` — `build()` raises `NotImplementedError("coming soon...")`.
* `src/rezplugins/build_process/remote.py:24` — `release()` raises the same.
* `src/rezplugins/build_process/remote.py:27-28` — `register_plugin()` returns the class, which is
  why `remote` appears in `--process` choices.
* `src/rezplugins/build_process/rezconfig.py` is effectively empty (2 lines: licence header).
* Corroborated by the config comment: *"Only 'local' build process is currently available"* —
  `src/rez/rezconfig.py:824-825`.

There is **no** remote-build protocol, transport, or host-selection specification anywhere in 3.4.0.
`ABSENT — searched: src/rezplugins/build_process/`, `grep -rn "remote" src/rez/build_process.py`
(no remote implementation), `src/rez/rezconfig.py` (no remote settings).

---

## 9. `build_time` / `timestamp`

### 9.1 `build_time` is not a Rez field

`ABSENT — searched: grep -rn "build_time" src/ --include=*.py`. The only hits are in the vendored
`distlib` copy (`src/rez/vendor/distlib/database.py:322`,
`src/rez/vendor/distlib/locators.py:1208`, `:1291`, `:1292`) and are a distlib concept, unrelated to
Rez packages. **The Rez-native name for "when this was built/released" is `timestamp`.**

### 9.2 Where `timestamp` is written

```python
# src/rezplugins/package_repository/filesystem.py:1433-1435
# timestamp defaults to now if not specified
if not package_data.get("timestamp"):
    package_data["timestamp"] = int(time.time())
```

* Written into the **installed package definition file** (`package.py` / `package.yaml`), not into a
  sidecar — dump at `src/rezplugins/package_repository/filesystem.py:1445-1451`.
* It is a **package-level** attribute, not per-variant. When a variant is added to an existing
  package, the existing `timestamp` is preserved — this is deliberate, see the comment at
  `src/rezplugins/package_repository/filesystem.py:1419-1421` and the release-key merge at
  `:1315-1319` + `:1393`.
* Schema: `Optional("timestamp"): int` — `src/rez/package_resources.py:164`
  (POD form `:255`).
* It is one of the seven release-time keys: `package_release_keys` —
  `src/rez/package_resources.py:32-39` = `timestamp`, `revision`, `changelog`, `release_message`,
  `previous_version`, `previous_revision`, `vcs`.

### 9.3 Determinism and overridability

**Not deterministic by default** — it is `int(time.time())` at install time
(`src/rezplugins/package_repository/filesystem.py:1435`).

**Overridable, but only in one specific case.** `timestamp` flows through the `overrides` argument
of `install_variant`. The override rule is:

```python
# src/rezplugins/package_repository/filesystem.py:1423-1431
for key, value in overrides.items():
    if existing_package:
        if key not in package_data:
            package_data[key] = value
    else:
        if value is self.remove:
            package_data.pop(key, None)
        else:
            package_data[key] = value
```

* Installing into a **new** package: `overrides["timestamp"]` wins (`:1427-1431`).
* Installing into an **existing** package: the existing value wins; the override is ignored unless
  the key is absent (`:1424-1426`).

`variant.install(path, dry_run=False, overrides=None)` — `src/rez/packages.py:454-484` — is the
public entry point; `overrides` is documented at `:468-469`.

`self.remove` is the `PackageRepository.remove` sentinel — `src/rez/package_repository.py:79`.

**Environment override:** there is **no** `REZ_TIMESTAMP`-style env var, because `timestamp` is not a
config setting. The general env-var mechanism (`REZ_<SETTING>`, `src/rez/config.py:87-89`) does not
apply. The only lever is the `overrides` dict passed by API callers. Notably
`copy_package()` injects a fresh timestamp unless `keep_timestamp=True`:

```python
# src/rez/package_copy.py:236-237
```

(also flagged in §D.21: `rez cp -k/--keep-timestamp`, `src/rez/cli/cp.py:40-43`, is ignored when
copying into an existing package).

**Backwards-compatible read path:** packages released by rez < 2.0.BETA.16 store the timestamp in
`release.yaml`, and rez-1 packages in `.metadata/release_time.txt`; both are migrated into
`timestamp` on load — `src/rezplugins/package_repository/filesystem.py:206-207` (the `not in data`
probe), `:213-245` (`_load_old_formats`), with the rez-1 read at `:233` and the int coercion at
`:237`.

---

# B. Test

## 10. `rez test` CLI

`src/rez/cli/test.py` (121 lines). Every flag — `setup_parser`, `:11-44`:

| Flag | Line | Meaning |
|---|---|---|
| `-l`, `--list` | `:12-14` | List the package's tests and exit. |
| `--dry-run` | `:15-18` | Show what tests would have been run, but do not run them. |
| `-s`, `--stop-on-fail` | `:19-21` | Stop on first test failure. |
| `--inplace` | `:22-25` | Run tests in the current environment. Any test whose requirements are not met by the current environment is skipped. |
| `--extra-packages PKG [PKG …]` | `:26-28` | Extra packages to add to the test environment. |
| `--paths PATH` | `:29-31` | Set package search path. |
| `--nl`, `--no-local` | `:32-34` | Don't load local packages. |
| `PKG` (positional, required) | `:35-37` | Package to run tests on. |
| `TEST` (positional, 0+) | `:38-40` | Tests to run (run all if not provided). |

Mutual exclusion is enforced manually (`argparse` cannot express cross-group exclusion — comment at
`:53`): `--inplace` cannot be combined with `--extra-packages` / `--paths` / `--no-local`
(`:54-58`).

`--paths` is split on `os.pathsep` and `expanduser`-ed (`:64-65`). `--no-local` maps to
`config.nonlocal_packages_path` (`:60-62`).

Extra args after `--` may only be passed to a **single** named test (`:67-73`).

Runner construction and exit: `:76-121`. Exit code is the **first non-zero test return code**
(`:109-121`); "no tests found" and "no tests with 'default' run_on tag" both exit `0`
(`:89-91`, `:102-107`).

### Flags that do **not** exist on `rez test`

| Flag asked about | Status | Evidence |
|---|---|---|
| `--no-safe` | **ABSENT** | `grep -rn "no_safe\|\"safe\"\|'safe'\|safe_mode" src/rez/package_test.py src/rez/cli/test.py` → zero hits. There is no "safe mode" concept in Rez testing. |
| `--clean` | **ABSENT** | Not in `src/rez/cli/test.py` (read in full, 121 lines). `--clean` exists on `rez build` (`src/rez/cli/build.py:88-90`) and `rez pkg-cache` (`src/rez/cli/pkg-cache.py:38-41`). |
| `--extra-package` (singular) | **ABSENT** — the flag is plural `--extra-packages` (`src/rez/cli/test.py:27`). | |

---

## 11. `package_test.py`

`src/rez/package_test.py` (750 lines).

### 11.1 There are no reserved runner function names

`ABSENT — searched: grep -rn "rez:setup\|rez:test\|rez:teardown" . --include=*.py --include=*.rst
--include=*.md` (whole clone, code and docs) → **zero hits**. Also
`grep -rn '"rez:' src/ --include=*.py` → zero hits.

Rez 3.4.0 tests are **arbitrary commands**, not Python functions with reserved names. A test entry
is either a command string, a command list, or a dict with a `"command"` key —
`PackageTestRunner` docstring `src/rez/package_test.py:22-51`, normalised at
`_get_test_info` `:549-552`:

```python
# src/rez/package_test.py:549-552
if not isinstance(test_entry, dict):
    test_entry = {
        "command": test_entry
    }
```

The only *function-shaped* hook is the rex attribute **`pre_test_commands`**, which is a
package.py-level rex function (schema `src/rez/package_resources.py:161`, in `package_rex_keys`
`:51-57`), executed per test at `src/rez/package_test.py:448-462`. It binds `this` (the variant) and
`test` with a single field, `name` (namespace built at `:454-456`, `executor.bind("test", ...)` at
`:460`).

### 11.2 There is no test-framework detection

`ABSENT — searched: grep -rn "pytest\|unittest" src/rez/ src/rezplugins/ --include=*.py` → the only
hit is the illustrative docstring example `src/rez/package_test.py:32`:

```python
"unit": "python -m unittest -s {root}/tests",
```

Rez does not detect, invoke, or parse the output of pytest/unittest. It runs the command and looks
**only at the exit code**.

### 11.3 Exit-code semantics

```python
# src/rez/package_test.py:463-489  (run_test inner loop)
retcode, _, _ = context.execute_shell(
    command=command,
    actions_callback=_pre_test_commands,
    stdout=self.stdout,
    stderr=self.stderr,
    block=True
)

if retcode:
    print_warning("Test command exited with code %d", retcode)
    self._add_test_result(test_name, variant, "failed",
                          "Test failed with exit code %d" % retcode)
    if not exitcode:
        exitcode = retcode
    if self.stop_on_fail:
        self.stopped_on_fail = True
        return exitcode
    continue
```

* Non-zero retcode ⇒ that (test, variant) pair is recorded `"failed"`; the first non-zero retcode is
  propagated as `run_test`'s return value (`:472-489`).
* Zero ⇒ `"success"` (`:491-497`).
* Additional recorded statuses: `"skipped"` for an unresolvable variant (`:404-409`), and `"skipped"`
  with `"Dry run mode"` under `--dry-run` (`:439-446`).
* `PackageTestResults` tallies: `num_tests` `:689-693`, `num_success` `:695-700`,
  `num_failed` `:702-707`, `num_skipped` `:708-712`; `add_test_result` `:713-722`;
  `print_summary` `:724-750`.
* Runner-level mirrors: `num_tests` `:228-232`, `num_success` `:234-238`, `num_failed` `:240-244`,
  `num_skipped` `:246-250`.

### 11.4 Other notable semantics

* **One common timestamp** is used across all tests so packages cannot appear mid-run —
  `self.timestamp = int(time.time())` at `:101-103`, passed to `ResolvedContext` at `:624`.
* Test contexts are **cached by requirement tuple** and reused between tests — `:608-629`.
* `testing=True` is passed to the resolved context — `:625`.
* Tests run against a resolved context containing the package (`:557-561`) plus the test's own
  `requires` (`:563-564`) plus `--extra-packages` (`:566-568`).
* Default `run_on` is `["default"]` — `:570-576`; `find_requested_test_names` uses fnmatch globbing
  over test names (`:212-226`).

---

## 12. Post-install tests

### 12.1 Schema

`tests_schema` — `src/rez/package_resources.py:101-121`:

```python
tests_schema = Schema({
    Optional(str): Or(
        Or(str, [str]),
        extensible_schema_dict({
            "command": Or(str, [str]),
            Optional("requires"): [
                Or(PackageRequest, And(str, Use(PackageRequest)))
            ],
            Optional("run_on"): Or(str, [str]),
            Optional("on_variants"): Or(
                bool,
                {
                    "type": "requires",
                    "value": [
                        Or(PackageRequest, And(str, Use(PackageRequest)))
                    ]
                }
            )
        })
    )
})
```

Attached to the package/variant schema as `Optional('tests'): late_bound(tests_schema)` —
`src/rez/package_resources.py:154` (POD `:247`, maker `src/rez/package_maker.py:78`).

Recognised keys: `command`, `requires`, `run_on`, `on_variants`.

**Documentation drift to be aware of:** the `PackageTestRunner` docstring shows a `"replace": True`
key (`src/rez/package_test.py:33-37`) that is **not** in the schema — `replace` is not a supported
`tests` key in 3.4.0 (searched `src/rez/package_test.py` and `tests_schema`; the only occurrence is
the docstring at `:36`). The schema uses a catch-all `Optional(str)` only at the *top* level
(test-name keys), not inside the test dict.

### 12.2 When they run

Post-install tests are driven from `_run_tests(variant, run_on, package_install_path)` —
`src/rezplugins/build_process/local.py:449-519`.

The mechanism (docstring at `:450-461`): the variant payload is installed, then the variant is
installed **into a temporary repository** so that only `package.py` is created there, with its root
redirected at the real payload via the `_redirected_base` attribute (`:484-489`); the temp repo is
prepended to the packages path so the temp variant is guaranteed to be resolved (`:491-493`).

Two trigger points, both **pre-install** despite living in a method named `_run_tests`:

| Context | `run_on` tag | Call site |
|---|---|---|
| `rez build --install` | `["pre_install"]` | `src/rezplugins/build_process/local.py:374-379` |
| `rez release` | `["pre_release"]` | `src/rezplugins/build_process/local.py:428-433` |

Test selection uses `PackageTestRunner.get_package_test_names(package, run_on=..., ran_once=...)`
(`:465-469`), which filters by `run_on` overlap (`:157-174`) and skips tests already run once when
`on_variants` is false (`:176-191`).

Failure handling — install/release is aborted and the payload removed:

```python
# src/rezplugins/build_process/local.py:514-519
if runner.num_failed:
    print('')
    raise PackageTestError(
        "%d tests failed; the installation has been cancelled"
        % runner.num_failed
    )
```

(preceded by `self._rmtree(build_result["variant_install_path"])` and
`cancel_variant_install()` at `:380-387` / `:434-441`.)

### 12.3 Environment variables set for tests

**No test-specific `REZ_TEST_*` environment variables exist.**
`ABSENT — searched: grep -rn "REZ_TEST" src/` → zero hits.

A test runs inside an ordinary `ResolvedContext` (`src/rez/package_test.py:619-627`), so it sees the
normal context variables, **plus** whatever `pre_test_commands` emits. The only test-scoped bindings
are the two rex names in `pre_test_commands` — `this` (variant) and `test` with field `name` —
`src/rez/package_test.py:455-461`.

---

# C. Release

## 13. `rez release` CLI

`src/rez/cli/release.py` (151 lines). Every flag — `setup_parser`, `:15-42`:

| Flag | Line | Meaning |
|---|---|---|
| `-m`, `--message MSG` | `:20-22` | Release message. |
| `--vcs TYPE` | `:23-25` | Force the VCS type to use; `choices` = `get_release_vcs_types()`. |
| `--no-latest` | `:26-28` | Allows release of a version earlier than the latest release. |
| `--ignore-existing-tag` | `:29-33` | Release even if the repo is already tagged at the current version. No effect if `plugins.release_vcs.check_tag` is false. |
| `--skip-repo-errors` | `:34-38` | Release even if repository-related errors occur. Carries an explicit "DO NOT use this option unless you absolutely must" warning. |
| `--no-message` | `:39-41` | Do not prompt for a release message. |

Plus everything from `setup_parser_common` (`src/rez/cli/build.py:35-84`), invoked at `:42`:
`--process`, `-b/--build-system`, `--variants`, `--ba/--build-args`, `--cba/--child-build-args`
(§A.6.2).

### `--dry-run` does not exist

`ABSENT` on the CLI — `src/rez/cli/release.py:15-42` (read in full) contains no `--dry-run`.
Dry-run *does* exist one level down in the API, and is used internally:
`Variant.install(path, dry_run=True)` (`src/rez/packages.py:454-467`) →
`repo.install_variant(..., dry_run=True)` (`:476-478`), which `LocalBuildProcess._release_variant`
uses to skip already-released variants (`src/rezplugins/build_process/local.py:398-404`). It is not
surfaced as a `rez release` flag.

### Release-message prompting

`src/rez/cli/release.py:82-140`. Gated on `config.prompt_release_message`
(`src/rez/rezconfig.py:804`, default `False`) **and** not `--message` **and** not `--no-message`
(`:86`). The message file is `rez-release-message-<sha1(working_dir)>.txt` under `config.tmpdir`
(`:87-91`); the changelog is appended after a `###<CHANGELOG>` token for reference and stripped back
out (`:93-125`); `config.editor` is invoked (`:115`); an empty message prompts `[A]bort or
[C]ontinue` (`:132-139`).

Release is executed at `:142-143`; the temp message file is removed at `:145-150`.

---

## 14. Release phases

Driven by `LocalBuildProcess.release()` — `src/rezplugins/build_process/local.py:90-147`, with the
VCS/release checks in `BuildProcessHelper`.

| # | Phase | Implementation | Line |
|---|---|---|---|
| 1 | **Pre-release validation** (`pre_release()`) | `src/rez/build_process.py:301-347` | called `local.py:94` |
| 1a | — release path must exist | `src/rez/build_process.py:304-307` | |
| 1b | — `vcs.validate_repostate()` | `:310-313` | |
| 1c | — existing-tag check (opt-in) | `:315-326` | |
| 1d | — package UUID mismatch check | `:328-337` | |
| 1e | — newer-version check (`ensure_latest`) | `:339-347` | |
| 2 | **Collect release data** (`get_release_data()`) | `src/rez/build_process.py:414-448` | `local.py:97` |
| 3 | **Run `pre_release` hooks** | `src/rez/build_process.py:369-388` | `local.py:103-109` |
| 4 | **Per-variant release** (`visit_variants(self._release_variant)`) | `src/rezplugins/build_process/local.py:394-447` | `local.py:112-115` |
| 4a | — skip if the destination variant already exists | `:398-404` | |
| 4b | — build + install payload with `BuildType.central` | `:414-420` | |
| 4c | — run `pre_release` tests | `:428-433` | |
| 4d | — `variant.install(release_path, overrides=release_data)` | `:443-446` | |
| 5 | **Run `post_release` hooks** | `src/rez/build_process.py:369-388` | `local.py:122-128` |
| 6 | **Post-release: create the VCS tag** (`post_release()`) | `src/rez/build_process.py:349-357` | `local.py:130-132` |
| 7 | **Print release summary** | `src/rezplugins/build_process/local.py:134-147` | |

Note `release_data["release_message"]` is injected at `local.py:445` before install.

### Rollback behaviour per phase

| Failure point | What is rolled back | Line |
|---|---|---|
| Phase 1 (any validation error) | **Nothing has happened yet** — no payload written, no tag created. Pure pre-flight; raises `ReleaseError`. | `src/rez/build_process.py:307`, `:326`, `:337`, `:343-345` |
| Phase 3 (`pre_release` hook raises `ReleaseHookCancellingError`) | Nothing yet; the release aborts before any variant is built. | `src/rez/build_process.py:379-383` |
| Phase 4b — build system returns `success=False` | The partially installed payload is `rmtree`d and `pkg_repo.on_variant_install_cancelled()` is called; `BuildError` propagates. | `local.py:276-281` then `:421-425` |
| Phase 4c — a `pre_release` test fails | The installed payload is `rmtree`d, `on_variant_install_cancelled()` is called, `PackageTestError` propagates. | `local.py:434-441` |
| Phase 5 (`post_release` hook) | **No rollback.** A `ReleaseHookCancellingError` here still leaves the variants released; only the exception is raised. | `src/rez/build_process.py:379-383`; note `local.py:122-128` runs *after* `:112-115` |
| Phase 6 — tagging | Wrapped in `repo_operation()`, which **swallows** `ReleaseVCSError` when `skip_repo_errors` is set (printing "THE FOLLOWING ERROR WAS SKIPPED"). Otherwise it propagates. | `src/rez/build_process.py:202-208`, `:356-357` |

**Important asymmetry:** there is **no rollback of already-released earlier variants** if variant *N*
fails after variant *N-1* succeeded. `visit_variants` (`:210-239`) iterates sequentially and the
first exception aborts the run, leaving earlier variants installed and tagged-free. The release
summary reports this as "N of M releases were successful" with a warning
(`local.py:136-140`).

`repo_operation()` is the generic error-swallowing context manager:

```python
# src/rez/build_process.py:202-208
@contextmanager
def repo_operation(self):
    exc_type = ReleaseVCSError if self.skip_repo_errors else _NeverError
    try:
        yield
    except exc_type as e:
        print_warning("THE FOLLOWING ERROR WAS SKIPPED:\n%s" % str(e))
```

(`_NeverError` imported `src/rez/build_process.py:11`.)

---

## 15. `release_vcs` plugin family

### 15.1 Enumeration

| Plugin | Module | Class | Notes |
|---|---|---|---|
| `git` | `src/rezplugins/release_vcs/git.py` | `GitReleaseVCS` (`:21`), `name()` `:26-28` | Full implementation; uses `git` / `git-python` (`dulwich`-style vendored import at `:14`). |
| `hg` | `src/rezplugins/release_vcs/hg.py` | `HgReleaseVCS` (`:18`), `name()` `:19-21` | Mercurial. `tag_exists` `:161`, `create_release_tag` `:244`. |
| `svn` | `src/rezplugins/release_vcs/svn.py` | `SvnReleaseVCS` (`:60`), `name()` `:61-63` | Subversion. `create_release_tag` `:129`. |
| `stub` | `src/rezplugins/release_vcs/stub.py` | `StubReleaseVCS` (`:16`), `name()` `:26-28` | Testing VCS: valid root is a `.stub` file (`:30-32`); tags are written to that YAML file (`:58-68`, `:70-76`). |

Plus `src/rezplugins/release_vcs/rezconfig.py` (`:1-47`) — plugin-wide defaults (§C.16).

Selection: `create_release_vcs(path, vcs_name=None)` — `src/rez/release_vcs.py:23-69`. With no
`--vcs`, every plugin's `find_vcs_root(path)` is tried and the **closest** root wins
(`:33-40`, `:60-61`); ties at the same level raise `ReleaseVCSError` naming the candidates
(`:62-66`). The comment at `:48-58` documents this "closest wins" rule.

### 15.2 The contract

`ReleaseVCS` — `src/rez/release_vcs.py:72`. Abstract-by-`NotImplementedError` members:

| Method | Signature / kind | Line |
|---|---|---|
| `name` | `@classmethod -> str` | `:91-94` |
| `is_valid_root` | `@classmethod (path) -> bool` | `:104-113` |
| `search_parents_for_root` | `@classmethod -> bool` | `:115-120` |
| `validate_repostate` | `(self) -> None` | `:142-144` |
| `get_current_revision` | `(self) -> object` | `:146-155` |
| `get_changelog` | `(self, previous_revision=None, max_revisions=None) -> str` | `:157-172` |
| `tag_exists` | `(self, tag_name) -> bool` | `:174-183` |
| `create_release_tag` | `(self, tag_name, message=None) -> None` | `:185-195` |
| `export` | `@classmethod (revision, path) -> None` | `:197-209` |

Concrete helpers provided by the base class:

* `__init__(pkg_root, vcs_root=None)` — `:75-89`; sets `self.vcs_root`, `self.pkg_root`,
  `self.package` (`:87`), `self.type_settings = ...plugins.release_vcs` (`:88`) and
  `self.settings = self.type_settings.get(self.name())` (`:89`). **This is how a VCS plugin reads its
  own settings.**
* `find_executable(name)` — `:96-102`.
* `find_vcs_root(path) -> (vcs_root, levels_up) | None` — `:122-140`; walks up if
  `search_parents_for_root()` (`:133-136`).
* `_cmd(*nargs)` — `:211-226`; runs the VCS binary with `cwd=self.pkg_root`.

`get_current_revision` may return **any type** as long as it carries enough information for `export`
— docstring note at `:150-154`.

### 15.3 Git implementation details worth citing

`validate_repostate()` — `src/rezplugins/release_vcs/git.py:93-142` — enforces, in order:
not a bare repo (`:94-96`); an upstream branch exists unless
`plugins.release_vcs.git.allow_no_upstream` (`:98-106`); the current branch matches
`releasable_branches` if that list is non-empty (`:108-122`); no uncommitted changes
(`:124-131`); not ahead/behind the remote (`:133-142`).

`get_current_revision()` — `:166-200` — returns a dict with `commit`, plus `branch`,
`tracking_branch`, `fetch_url`, `push_url` when available.

`get_changelog()` — `:144-164` — `git log -n <max_revisions> <prev_commit>..HEAD`; note the comment
at `:158-159`: git falls back to the last common ancestor, so a previous release from a different
branch is handled.

---

## 16. Tag policy

### 16.1 Tag naming

Configurable, formatted from the package — `src/rezplugins/release_vcs/rezconfig.py:5-12`:

```python
# Format string used to determine the VCS tag name when releasing. This
# will be formatted using the package being released - any package
# attribute can be referenced in this string, eg "{name}".
#
# It is not recommended to write only '{version}' to the tag. This will
# cause problems if you ever store multiple packages within a single
# repository - versions will clash and this will cause several problems.
tag_name = "{qualified_name}"
```

* Default: `"{qualified_name}"` — `src/rezplugins/release_vcs/rezconfig.py:12`.
  (`qualified_name` is `{name}-{version}`; the property is at `src/rez/packages.py:243` for
  `Package` and `:380` for `Variant`.)
* It is a **format string over the package**, not a fixed `{name}-{version}` literal — resolved at
  `BuildProcessHelper.get_current_tag_name()`:

```python
# src/rez/build_process.py:359-367
def get_current_tag_name(self) -> str:
    release_settings = self.package.config.plugins.release_vcs
    try:
        tag_name = self.package.format(release_settings.tag_name)
    except Exception as e:
        raise ReleaseError("Error formatting release tag name: %s" % str(e))
    if not tag_name:
        tag_name = "unversioned"
    return tag_name
```

Fallback when the format yields an empty string: `"unversioned"` (`:365-366`).

### 16.2 An existing tag must not be moved

Two independent guards:

1. **Pre-flight refusal** — opt-in via `check_tag`:

```python
# src/rez/build_process.py:315-326
if release_settings.check_tag and not self.ignore_existing_tag:
    tag_name = self.get_current_tag_name()
    tag_exists = False
    with self.repo_operation():
        tag_exists = self.vcs.tag_exists(tag_name)

    if tag_exists:
        raise ReleaseError(
            "Cannot release - the current package version '%s' is "
            "already tagged in the repository. Use --ignore-existing-tag "
            "to force the release" % self.package.version)
```

`check_tag` defaults to **`False`** — `src/rezplugins/release_vcs/rezconfig.py:42`, with a long
comment at `:21-41` explaining the multi-site rationale.

2. **`create_release_tag` is a no-op if the tag already exists** — the plugins never move/force a tag:

```python
# src/rezplugins/release_vcs/git.py:206-208
def create_release_tag(self, tag_name, message=None) -> None:
    if self.tag_exists(tag_name):
        return
```

The same guard exists in the stub plugin, which additionally warns:

```python
# src/rezplugins/release_vcs/stub.py:62-64
elif tag_name in data["tags"]:
    print_warning("Skipped tag creation, tag '%s' already exists" % tag_name)
    return
```

`git` then creates an **annotated** tag (`git tag -a <name> -m <message>`) and pushes it to the
tracking remote — `src/rezplugins/release_vcs/git.py:210-223`. No `--force`, no tag deletion
anywhere.

The tag is created **last**, in `post_release()` — `src/rez/build_process.py:349-357` (called from
`local.py:130-132`), and only if at least one variant was released (`local.py:131`).

Branch restriction is a separate, configurable policy: `releasable_branches`
(`src/rezplugins/release_vcs/rezconfig.py:14-19`, default `[]` = no restriction), enforced at
`src/rezplugins/release_vcs/git.py:108-122`.

---

## 17. `release_hook` plugin family

### 17.1 Enumeration

| Plugin | Module | Class | `name()` | Hooks implemented |
|---|---|---|---|---|
| `amqp` | `src/rezplugins/release_hook/amqp.py` | `AmqpReleaseHook` (`:17`) | `:48` | `post_release` (`:54`) |
| `command` | `src/rezplugins/release_hook/command.py` | `CommandReleaseHook` (`:24`) | `:52` | `pre_release` (`:111`), `post_release` (`:124`) |
| `emailer` | `src/rezplugins/release_hook/emailer.py` | `EmailReleaseHook` (`:19`) | `:31` | `post_release` (`:37`) |

Plus `src/rezplugins/release_hook/rezconfig.py` (`:94-104` region) — per-plugin defaults, and
`emailer-recipients-example.yaml` (a sample recipients file).

Enabled by listing names in the `release_hooks` config setting — `src/rez/rezconfig.py:800`
(documented `:795-799`: *"a release hook plugin being loaded does not mean it will run. It needs to
be listed here as well"*).

### 17.2 The contract

`ReleaseHook` — `src/rez/release_hook.py:39`.

* `name()` — `@classmethod`, `:46-49` (`raise NotImplementedError`).
* `__init__(source_path)` — `:51-60`; sets `self.source_path` (`:57`),
  `self.package = get_developer_package(source_path)` (`:58`),
  `self.type_settings = self.package.config.plugins.release_hook` (`:59`),
  `self.settings = self.type_settings.get(self.name())` (`:60`).

**This is how a release hook reads its own settings** — `self.settings` is the sub-dict of
`plugins.release_hook.<hook_name>`, sourced from the plugin's `rezconfig` defaults merged with any
package-level `config` override.

Hook methods (all default `pass`; raise `ReleaseHookCancellingError` to cancel):

| Method | Signature | Line |
|---|---|---|
| `pre_build` | `(user, install_path, variants=None, release_message=None, changelog=None, previous_version=None, previous_revision=None, **kwargs)` | `:62-84` |
| `pre_release` | `(user, install_path, variants=None, release_message=None, changelog=None, previous_version=None, previous_revision=None, **kwargs)` | `:86-110` |
| `post_release` | `(user, install_path, variants, release_message=None, changelog=None, previous_version=None, previous_revision=None, **kwargs)` | `:112-131` |

`post_release`'s `variants` is positional and is the list of *released* `Variant` objects
(`:122`).

**Config schema per hook.** A hook declares `schema_dict`, which Rez folds into
`plugins.release_hook.<name>` — the aggregation is
`RezPluginType.get_plugin_config_data()`-style merging at
`src/rez/plugin_managers.py:290-293`:

```python
# src/rez/plugin_managers.py:288-293
if plugin_class.schema_dict:
    d_ = {name: plugin_class.schema_dict}
    deep_update(d, d_)
return dict_to_schema(d, required=True, modifier=expand_system_vars)
```

Examples: `AmqpReleaseHook.schema_dict` — `src/rezplugins/release_hook/amqp.py:37`;
`CommandReleaseHook.schema_dict` — `src/rezplugins/release_hook/command.py:40` (with a
`commands_schema` at `:26`); `EmailReleaseHook.schema_dict` —
`src/rezplugins/release_hook/emailer.py:21`.

### 17.3 Dispatch

`ReleaseHookEvent` — `src/rez/release_hook.py:134-143`:

```python
class ReleaseHookEvent(Enum):
    """Enum to help manage release hooks."""
    pre_build = ("pre-build", "build", "pre_build")
    pre_release = ("pre-release", "release", "pre_release")
    post_release = ("post-release", "release", "post_release")

    def __init__(self, label, noun, func_name) -> None:
        self.label = label
        self.noun = noun
        self.__name__ = func_name
```

`BuildProcessHelper.run_hooks(hook_event, **kwargs)` — `src/rez/build_process.py:369-388`:
instantiates hooks from `self.package.config.release_hooks` (`:370-371`), then `getattr(hook,
hook_event.__name__)` and calls it with `user=getpass.getuser()` plus kwargs (`:377-378`).
`ReleaseHookCancellingError` → `ReleaseError` naming the hook (`:379-383`); other `RezError`s are
logged only (`:384-387`).

Only **two** of the three events are actually dispatched in 3.4.0 — `pre_release`
(`local.py:103-109`) and `post_release` (`local.py:122-128`). **`pre_build` is never dispatched by
the build/release code path** (searched `src/rezplugins/build_process/local.py` and
`src/rez/build_process.py` — no `ReleaseHookEvent.pre_build` usage); it is defined in the contract
for third parties.

---

## 18. `release_message`, `release_path` / `packages_path`

| Concept | Location | Notes |
|---|---|---|
| `release_message` (package attribute) | `src/rez/package_resources.py:167` | `Optional('release_message'): Or(None, str)`; POD form `:258`. |
| `release_message` (set at release) | `src/rezplugins/build_process/local.py:445` | `release_data["release_message"] = release_message`. |
| `release_message` (passed to hooks) | `local.py:106`, `:126` | Part of the hook kwargs. |
| `release_message` (release key) | `src/rez/package_resources.py:32-39` | In `package_release_keys`. |
| `release_packages_path` | `src/rez/rezconfig.py:73` | Default `"~/.rez/packages/int"`; documented `:68-72` as where `rez-release` deploys. |
| `local_packages_path` | `src/rez/rezconfig.py:69` | Default `"~/packages"`; documented `:68` as where `rez-build` installs. |
| `packages_path` | `src/rez/rezconfig.py:62-67` | Default 3-entry list `["~/packages", "~/.rez/packages/int", "~/.rez/packages/ext"]`; "a package with the same name and version in an earlier path takes precedence" (`:60-61`). |
| `nonlocal_packages_path` | used `src/rez/build_process.py:266-269` | `packages_path` for local builds, `nonlocal_packages_path` for central. |

**There is no setting literally named `release_path`.** The name is `release_packages_path`
(`src/rez/rezconfig.py:73`); `release_path` appears only as a local variable
(e.g. `src/rezplugins/build_process/local.py:395`, `src/rez/build_process.py:305`, `:390`).

Read sites: `self.package.config.release_packages_path` — `src/rezplugins/build_process/local.py:96`,
`:395`; `src/rez/build_process.py:305`, `:390`; `src/rez/package_repository.py` consumers.

All are overridable via `REZ_RELEASE_PACKAGES_PATH` / `REZ_LOCAL_PACKAGES_PATH` /
`REZ_PACKAGES_PATH` per `src/rez/config.py:87-89`.

---

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
parts = path.split('@', 1)
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
    "glob": GlobRule, "regex": RegexRule, "range": RangeRule,
    "before": TimestampRule, "after": TimestampRule}

label, txt = Rule._parse_label(txt)
if label is None:
    if '*' in txt:
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

# E. Ecosystem surface

## 23. Individual capability statements

### `rez bind`

- **Entry points:** `setup_parser` `src/rez/cli/bind.py:13`, `command` `src/rez/cli/bind.py:42`;
  engine `bind_package` `src/rez/package_bind.py:81`, `_bind_package` `src/rez/package_bind.py:153`,
  `get_bind_modules` `src/rez/package_bind.py:23`, `find_bind_module` `src/rez/package_bind.py:49`.
- **Capability:** Turns software already present on the current system into a real Rez package
  installed into a package repository path.
- **What it binds** — a bind module is one `.py` file in `src/rez/bind/` whose *filename stem is the
  package name*; discovery also walks `config.bind_module_path` (`src/rez/config.py:399`, default
  `[]` at `src/rez/rezconfig.py:140`) and skips stems starting with `_`
  (`src/rez/package_bind.py:29-46`):

| Module | `bind()` | Creates |
|---|---|---|
| `arch.py` | `src/rez/bind/arch.py:14` | `arch`, version = `system.arch` |
| `platform.py` | `src/rez/bind/platform.py:14` | `platform`, version = `system.platform` |
| `os.py` | `src/rez/bind/os.py:14` | `os`; `requires = ["platform-<p>", "arch-<a>"]` (`:19-22`) |
| `python.py` | `src/rez/bind/python.py:40` | `python` from an interpreter; `--exe` (`:18`) |
| `rez.py` | `src/rez/bind/rez.py:21` | Rez itself; `requires = ["python-3.8+<3.14"]` (`:34`) |
| `rezgui.py` | `src/rez/bind/rezgui.py:35` | `rez-gui`; `--gui-lib` default `PyQt-4` (`:19-22`) |
| `pip.py` | `src/rez/bind/pip.py:11` | the `pip` module + `pip` tool |
| `setuptools.py` | `src/rez/bind/setuptools.py:11` | `setuptools` + `pkg_resources`, deliberately no tools (`:15-20`) |
| `sip.py` | `src/rez/bind/sip.py:12` | `sip` |
| `PyQt.py` | `src/rez/bind/PyQt.py:12` | `PyQt`, tool `pyuic4`, `requires=["sip-4"]` |
| `PySide.py` | `src/rez/bind/PySide.py:11` | `PySide`, tool `pyuic4` |
| `cmake.py` | `src/rez/bind/cmake.py:25` | a `cmake` executable; `--exe` (`:16`) |
| `gcc.py` | `src/rez/bind/gcc.py:25` | `gcc` **and** `g++`; errors if versions differ (`:39-40`) |
| `hello_world.py` | `src/rez/bind/hello_world.py:43` | the `hello_world` test package at `1.0` |
| `_pymodule.py` | `src/rez/bind/_pymodule.py:59` | shared helper, not a package |
| `_utils.py` | — | helpers (`find_exe`:61, `extract_version`:85, `check_version`:49) |

- **Non-obvious facts:** bind modules are **executed, not imported**
  (`exec(compile(...))` at `src/rez/package_bind.py:160-162`, lookup at `:167`, `:178-180`); each
  module gets its own argparse sub-parser so `rez bind python --exe /path` is parsed by the module
  (`:165-170`, CLI forwards via `argparse.REMAINDER` at `src/rez/cli/bind.py:36-39`); `rez bind`
  **recursively binds dependencies** (`:134-138`, disabled by `--no-deps`, failures downgraded to
  warnings at `:124-126`, `:143`); `--quickstart` binds a fixed order-sensitive list
  (`src/rez/cli/bind.py:63-82`, "in dependency order, do not change" at `:64`).

### `rez pip`

- **Entry points:** `setup_parser` `src/rez/cli/pip.py:14`, `command` `src/rez/cli/pip.py:39`;
  engine `pip_install_package` `src/rez/pip.py:239`, `run_pip_command` `src/rez/pip.py:49`,
  `find_pip` `src/rez/pip.py:65`; conversion in `src/rez/utils/pip.py`.
- **Capability:** Runs pip and converts every resulting python distribution into a first-class Rez
  package in a Rez repository.
- **Integration mechanism:** pip is invoked as a **subprocess**, never imported as a library —
  `command = [py_exe, "-m", "pip"] + command_args` (`src/rez/pip.py:57`), with the python located by
  resolving a Rez `python` package (`find_pip_from_context` `:157`). Falls back to Rez's own venv pip
  with a warning (`:96-108`) and hard-fails if that pip is `<19` (`PIP_SPECIFIER` `:37`, check
  `:116-121`). Install command adds `--use-pep517` (`:292-293`), `--target=<mkdtemp>` (`:295-296`),
  and `--no-deps` in `InstallMode.no_deps` (`:298-299`). Artifacts are enumerated with the vendored
  **distlib** `DistributionPath` (`:321-323`), not by parsing pip output; files landing in `bin/`
  become Rez tools (`:370-374`). Each distribution becomes a package via `make_package` (`:406`) with
  `hashed_variants = True` (`:432-435`) and provenance attributes `from_pip`, `pip_name`,
  `is_pure_python` (`:438-440`). Name/version translation is mandatory because `-` is a Rez version
  separator: `dist_name.replace("-", "_")` (`src/rez/utils/pip.py:44`), PEP440 → Rez version at
  `src/rez/utils/pip.py:46`; purity from the wheel `Root-Is-Purelib` header (`:317`, `:341`).
- **Non-obvious:** the CLI **requires** `--install` (`src/rez/cli/pip.py:51-52`); `-r/--release`
  targets `release_packages_path` vs the default `local_packages_path` (`src/rez/pip.py:274-277`).

### `rez env`

- **Entry points:** `setup_parser` `src/rez/cli/env.py:11`, `command` `src/rez/cli/env.py:147`;
  shell launch `ResolvedContext.execute_shell` `src/rez/resolved_context.py:1442`.
- **Capability:** Resolves a request into a `ResolvedContext` and either opens a configured subshell,
  runs a command in it, or serialises it to an `.rxt` file.
- **Arg mode:** `grouped` — args split on `--` (`src/rez/cli/_util.py:37-39`).

| Group | Flags (all in `src/rez/cli/env.py`) |
|---|---|
| Shell / startup | `--shell`:20, `--rcfile`:24, `--norc`:28, `-c/--command`:31, `-s/--stdin`:38, `--new-session`:107, `--detached`:110, `--pre-command`:128 (hidden) |
| Request / resolve | `PKG`:130, `--ni/--no-implicit`:41, `--nl/--no-local`:45, `-b/--build`:48, `--paths`:51, `-t/--time`:54, `--max-fails`:59, `--time-limit`:63, `--exclude`:76, `--include`:80, `--no-filters`:84, `--no-cache`:97, `--fail-graph`:103, `--stats`:117, `--no-passive`:113 |
| Context I/O & patching | `-o/--output FILE`:67, `-i/--input FILE`:72, `-p/--patch`:88, `--strict`:91, `--patch-rank`:94 |
| Package caching | `--no-pkg-cache`:120, `--pkg-cache-mode {sync,async}`:123 |
| Output | `-q/--quiet`:100, `--N0`:133 (hidden); `-v/--verbose` added globally at `src/rez/cli/_main.py:67` |

- **Non-obvious:** `--input` and `PKG` are mutually exclusive **unless** patching (`:176-177`);
  patching without `--input` patches the *ambient* context from `$REZ_RXT_FILE` and fails hard if
  there is none (`:181-187`); patching **discards** the loaded context and re-resolves from scratch
  (`:190-193`); `-c/--command` and "args after `--`" are mutually exclusive (`:160-161`); exit code
  is `0/1` from the spawned shell (`:279`) while `-o` exits `0 if resolved else 1` (`:253`).
- **ABSENT** — searched `src/rez/cli/env.py` (whole file) and
  `grep -rn "no-rez-env\|view-pre\|view-post\|--suite\|--create" src/rez/cli/`: `--suite`,
  `--create`, `--view-pre`, `--view-post`, `--no-rez-env` do **not** exist on `rez env`. Suite
  visibility is instead a config policy, `suite_visibility` (`src/rez/config.py:434`).

### `rez context`

- **Entry points:** `setup_parser` `src/rez/cli/context.py:30`, `command`
  `src/rez/cli/context.py:112`. Serialisation: `ResolvedContext.to_dict`:1604, `from_dict`:1704,
  `save`:724, `write_to_buffer`:730, `load`:766, `read_from_buffer`:776,
  `serialize_version = (4, 9)` at `src/rez/resolved_context.py:175`.
- **Capability:** Loads the current (or a named/stdin) `.rxt` context and prints, diffs, interprets
  or graphs it.
- **Non-obvious:** the module **disables** context tracking and package caching at import time
  (`src/rez/cli/context.py:22-25`); an `.rxt` file is JSON but the reader is **format-agnostic** —
  content not starting with `{` is parsed as YAML (`src/rez/resolved_context.py:2043-2047`);
  serialisation is version-checked with a warning rather than a hard failure (`:1715-1730`); the
  "current" context is just `$REZ_RXT_FILE` (`src/rez/status.py:39`,
  `src/rez/resolved_context.py:745`).

### Suites

- **Entry points:** `setup_parser` `src/rez/cli/suite.py:11`, `command`
  `src/rez/cli/suite.py:89`; model `Suite` `src/rez/suite.py:48`, `Tool` TypedDict
  `src/rez/suite.py:27`, `Context` TypedDict `src/rez/suite.py:36`; visibility policy
  `SuiteVisibility` `src/rez/resolved_context.py:82`, applied in `_append_suite_paths`
  `src/rez/resolved_context.py:2274`.
- **Capability:** A *suite* is a directory of named contexts whose tools are exposed through one
  `bin/` directory of wrapper scripts that re-enter the right context.
- **CLI flags:** `-l/--list`:12, `-t/--tools`:15, `--which`:18, `--validate`:21, `--create`:24,
  `-c/--context`:27, `-i/--interactive`:31, `-a/--add`:34, `-P/--prefix-char`:37, `-r/--remove`:43,
  `-d/--description`:46 (declared but unused), `-p/--prefix`:49, `-s/--suffix`:52, `--hide`:55,
  `--unhide`:58, `--alias`:61, `--unalias`:64, `-b/--bump`:67, `--find-request`:70,
  `--find-resolve`:72, `DIR`:76.
- **The suite file is `suite.yaml`, not `.rez`.** `Suite.save` writes
  `os.path.join(path, "suite.yaml")` (`src/rez/suite.py:477`); `Suite.load` raises
  `SuiteError("Not a suite: %r")` if missing (`:517-521`). **ABSENT** — searched `src/rez/suite.py`,
  `src/rez/status.py`, `src/rez/config.py` for a `.rez` suite file: none exists in 3.4.0. On-disk
  shape: `<dir>/suite.yaml` + `<dir>/contexts/<name>.rxt` (`:704-709`) + `<dir>/bin/<alias>` (`:487`).
- **Non-obvious:** tool wrappers are **generated forwarding scripts**, not symlinks
  (`create_forwarding_script(..., func_name="_FWD__invoke_suite_tool_alias", ...)` at `:509-515`,
  target at `:787`); tool-name clashes resolve three-layered — explicit alias, then context
  prefix/suffix, then last-added wins (`:734-786`); visibility is an env-construction policy
  (`never/always/parent/parent_priority`, `src/rez/resolved_context.py:82-92`) not a suite property;
  a suite is "visible" iff its `bin` dir's parent contains a `suite.yaml` and that `bin` is on
  `$PATH` (`visible_suite_paths` `src/rez/suite.py:535`).

### Shell plugin family

**Every plugin in `src/rezplugins/shell/`** (discovery skips `_`-prefixed names and `rezconfig`,
`src/rez/plugin_managers.py:163-164`):

| File | Class | Line | Capability |
|---|---|---|---|
| `sh.py` | `SH(UnixShell)` | `src/rezplugins/shell/sh.py:23` | POSIX `sh`; `norc_arg='--noprofile'`:24 |
| `bash.py` | `Bash(SH)` | `src/rezplugins/shell/bash.py:18` | bash; `rcfile_arg='--rcfile'`:19, `norc_arg='--norc'`:20 |
| `zsh.py` | `Zsh(SH)` | `src/rezplugins/shell/zsh.py:22` | zsh; **no** `--rcfile` (`rcfile_arg=None`:23) |
| `csh.py` | `CSH(UnixShell)` | `src/rezplugins/shell/csh.py:25` | csh; `norc_arg='-f'`:26 |
| `tcsh.py` | `TCSH(CSH)` | `src/rezplugins/shell/tcsh.py:18` | tcsh; differs from csh only in name + `escape_string`:24 |
| `cmd.py` | `CMD(Shell)` | `src/rezplugins/shell/cmd.py:22` | Windows `cmd.exe`; `expand_env_vars=True`:28, `doskey` aliases (`:38`, `:326`) |
| `powershell.py` | `PowerShell(PowerShellBase)` | `src/rezplugins/shell/powershell.py:11` | Windows PowerShell 5; registered **only on Windows** (`:22-24`) |
| `pwsh.py` | `PowerShellCore(PowerShellBase)` | `src/rezplugins/shell/pwsh.py:11` | PowerShell Core 6+; platform-independent (`:32-34`) |
| `gitbash.py` | `GitBash(Bash)` | `src/rezplugins/shell/gitbash.py:23` | Git-for-Windows bash; forces `pathsep=':'`:26 |
| `_utils/` | `PowerShellBase` `src/rezplugins/shell/_utils/powershell_base.py:21`; `windows.py` `to_posix_path`:15, `to_windows_path`:38 | — | **Not a plugin** — leading underscore skipped (`src/rez/plugin_managers.py:163`) |
| `rezconfig.py` | — | `src/rezplugins/shell/rezconfig.py` | **Not a plugin** — name explicitly skipped; per-shell defaults |

**Contract — `Shell` in `src/rez/shells.py:74`** (`class Shell(ActionInterpreter)`, inheriting the
whole `ActionInterpreter` surface from `src/rez/rex.py:454`):

| Member | Where | Notes |
|---|---|---|
| `schema_dict` | `src/rez/shells.py:77` | `{"prompt": str}` — per-shell plugin config schema |
| `name()` | `:79` | abstract (`:83`) — the plugin name |
| `executable_name()` / `executable_filepath()` / `executable` | `:85` / `:91` / `:97` | |
| `is_available()` | `:101` | True iff the executable resolves (`:108-111`) |
| `file_extension()` | `:113` | abstract |
| `startup_capabilities(rcfile, norc, stdin, command)` | `:122` | abstract; returns the 4-tuple of *actually applied* options |
| `get_syspaths()` | `:139` | abstract (`:141`) |
| `spawn_shell(...)` | `:213` | abstract (`:257`) |
| `convert_tokens(value)` | `:259` | concrete |
| `get_key_token` / `get_all_key_tokens` | `:276` / `:291` | latter abstract (`:304`) |
| `line_terminator()` | `:306` | abstract (`:312`) |
| `join(command)` | `:314` | **concrete** default, unix-friendly escaping (`:326-341`) |
| `find_executable(name, check_syspaths)` | `:179` | honours `plugins.shell.<name>.executable_fullpath` first (`:193-199`) |
| `new_shell()` / `get_output()` / `_addline()` | `:163` / `:150` / `:147` | output rendering |

Inherited from `ActionInterpreter` (`src/rez/rex.py:454`), all abstract unless implemented:
`get_output`:488, **`setenv`**:501, **`unsetenv`**:504, **`resetenv`**:507, **`prependenv`**:510,
**`appendenv`**:515 (both optional *if* `setenv` is implemented, `:512`, `:517`), **`alias`**:520,
`info`:523, `error`:526, **`command`**:529, `comment`:532, **`source`**:535, **`shebang`**:538,
`get_key_token`:541, **`escape_string(value, is_path=False)`**:546 (default is a **no-op** returning
`str(value)`, `:566`), `_bind_interactive_rez`:616, `normalize_path`:574, `normalize_paths`:595,
`_saferefenv`:606. Class knobs: `expand_env_vars = False` (`:469`), `pathsep = os.pathsep` (`:474`,
overridden by gitbash), `ENV_VAR_REGEX` (`:478-482`).

Intermediate base `UnixShell` `src/rez/shells.py:344`: `rcfile_arg`/`norc_arg`/`histfile`/`histvar`/
`syspaths` (`:348-355`), `command_arg='-c'`, `stdin_arg='-s'`, `last_command_status='$?'`
(`:352-354`), `supports_norc`/`supports_command`/`supports_stdin` (`:361-371`) and abstract
`get_startup_sequence` (`:373`).

**Discovery:** `get_shell_types()` → `plugin_manager.get_plugins('shell')` (`src/rez/shells.py:32-39`);
`get_shell_class(shell)` (`:42-55`); `create_shell(shell, **kwargs)` (`:58-71`), both falling back to
`config.default_shell` (`src/rez/config.py:442`, default `""` at `src/rez/rezconfig.py:515`) then
`system.shell` (`src/rez/system.py:66`). Loading is the two-pass namespace + entry-point scheme
(§A.1.4). `Shell.__init__` binds `self.settings = config.plugins.shell[self.name()]`
(`src/rez/shells.py:143-145`).

**ABSENT:** `get_rezenv_*` — searched `grep -rn "get_rezenv" src/` → no matches. There is also no
top-level `shells` config key and no `shell_schema` key — searched `src/rez/config.py`,
`src/rez/rezconfig.py`: only `default_shell` (`:442`) exists. There is **no `python` shell plugin**;
the Python interpreter is a separate `ActionInterpreter` subclass, `Python` at `src/rez/rex.py:625`.

### `yaml2py`

- **Entry points:** `setup_parser` `src/rez/cli/yaml2py.py:11`, `command`
  `src/rez/cli/yaml2py.py:18`; conversion via `package.print_info(format_=FileFormat.py)`
  (`src/rez/cli/yaml2py.py:40`), `FileFormat` enum `src/rez/serialise.py:39`.
- **Capability:** Loads a `package.yaml` (path, directory, or cwd) and prints the equivalent
  `package.py` source.
- **Non-obvious:** it is a **print/inspect** tool, not a file rewriter — nothing is written to disk
  (`:18-40`).

### `rez plugins`

- **Entry points:** `setup_parser` `src/rez/cli/plugins.py:11`, `command`
  `src/rez/cli/plugins.py:24`; implementation in `src/rez/package_search.py`.
- **Capability:** Lists the **package plugins** of a given Rez package (plugin packages that extend
  `PKG`) — **not** Rez's own plugin types.
- **Flags:** `--paths` (`:12`), positional `PKG` (`:15`).
- **ABSENT:** there is **no CLI surface in 3.4.0 for listing Rez's own plugin types/classes** —
  searched `src/rez/cli/plugins.py` and
  `grep -rn "plugin-config-data\|validate-config-file\|--plugins\b" src/`: no `--plugins`,
  `--plugin-config-data` or `--validate-config-file` flag exists anywhere.

### `rez-depends`

- **Entry points:** `setup_parser` `src/rez/cli/depends.py:11`, `command`
  `src/rez/cli/depends.py:45`; implementation `get_reverse_dependency_tree` in
  `src/rez/package_search.py`.
- **Capability:** **Reverse** dependency lookup — which packages depend on `PKG` — optionally as a
  graph.
- **Flags:** `-d/--depth`:13, `--paths`:16, `-b/--build-requires`:19,
  `-p/--private-build-requires`:22, `-g/--graph`:25, `--pg/--print-graph`:28,
  `--wg/--write-graph`:31, `-q/--quiet`:34, `PKG`:36.
- **Deprecation status: NOT deprecated.** `src/rez/deprecations.py` is a 37-line warning helper
  (`warn`:9, `RezDeprecationWarning`:36) with **no mention of any command**; every call site is
  config-related (`src/rez/config.py:117`, `:138`, `:1076`). Searched `grep -rn "deprecat"
  src/rez/cli/` → no matches.

### `rez-search`

- **Entry points:** `setup_parser` `src/rez/cli/search.py:14`, `command`
  `src/rez/cli/search.py:69`; implementation `ResourceSearcher` /
  `ResourceSearchResultFormatter` in `src/rez/package_search.py`.
- **Capability:** Searches package repositories for packages, families or variants, with glob
  patterns, time filters, validation and custom output formatting.
- **Flags:** `-t/--type {package,family,variant,auto}`:20, `--nl/--no-local`:25, `--validate`:28,
  `--paths`:31, `-f/--format`:34, `--no-newlines`:38, `-l/--latest`:41, `-e/--errors`:45,
  `--nw/--no-warnings`:48, `--before`:51, `--after`:55, `PKG`:60.
- **Deprecation:** the command is not deprecated, but its `--sort` argument was deprecated and
  **removed in 3.0.0** (`CHANGELOG.md:375`, removal noted `CHANGELOG.md:268`).

### `rez config`

- **Entry points:** `setup_parser` `src/rez/cli/config.py:13`, `command`
  `src/rez/cli/config.py:33`.
- **Capability:** Prints the effective Rez configuration, a single dotted-path setting, or the list
  of config files searched/sourced.
- **Flags:** `--json`:14, `--search-list`:18, `--source-list`:22, positional `FIELD`:24.
- **Non-obvious:** the flag is **`--search-list` / `--source-list`, not `--list`** — the former
  prints `config.filepaths` (files Rez *looked* for), the latter `config.sourced_filepaths` (files it
  actually read), and both return before field handling (`:38-46`). `FIELD` is a dotted path with
  `ValueError("no such setting: %r")` on a miss (`:49-57`). Dict/list values render as YAML by
  default, JSON with `--json`, explicitly to produce `REZ_*_JSON` payloads (`:15-17`, `:59-65`).
- **ABSENT:** `--list`, `--plugins`, `--plugin-config-data`, `--validate-config-file` — searched
  `src/rez/cli/config.py` (whole file) and
  `grep -rn "plugin-config-data\|validate-config-file\|--plugins\b" src/`.

### `rez status`

- **Entry points:** `setup_parser` `src/rez/cli/status.py:11`, `command`
  `src/rez/cli/status.py:26`; model `Status` `src/rez/status.py:23`, singleton `status`
  `src/rez/status.py:379`.
- **Capability:** Reports whether you are inside a Rez context, which suites are visible on `$PATH`,
  and identifies a given object as a tool, package, context or suite.
- **Flags:** `-t/--tools`:13 (accepts a glob), positional `OBJECT`:17. Exit `0` if anything matched,
  `1` otherwise (`src/rez/cli/status.py:35`).
- **Non-obvious:** `OBJECT` is resolved by **trying four interpreters in order and reporting every
  match** — tool, package, suite, context (`src/rez/status.py:114-121`); "am I in a context?" is
  exactly `$REZ_RXT_FILE` (`:39`); `print_tools` colours three states including `(in conflict)` and
  `(hidden by unknown tool '<path>')` (`:146-153`, `:165-169`).

### `rez help`

- **Entry points:** `setup_parser` `src/rez/cli/help.py:10`, `command` `src/rez/cli/help.py:28`;
  model `PackageHelp` `src/rez/package_help.py:20`.
- **Capability:** Opens (or lists) the `help` entries declared by a package; with no package, opens
  the Rez technical manual.
- **Flags:** `-m/--manual`:11, `-e/--entries`:14, `PACKAGE`:17, `SECTION` (1-based, default 1):20.
- **Non-obvious:** help is **version-range aware** and picks the newest package in the range that
  declares `help` (`src/rez/package_help.py:38-44`); entries are a plain string or a list of
  `[name, uri]` pairs (`:50-54`); a "section" containing whitespace is treated as a **command** and
  `Popen`'d with `shell=True`, while single-token entries go to `webbrowser` (`:93-105`); a bad
  `SECTION` index exits **2** (`src/rez/cli/help.py:60-63`).

## 24. Full top-level command list

### 24.1 How the name is derived (authoritative)

There is exactly one source of truth for the subcommand set: the `subcommands` dict at
`src/rez/cli/_util.py:24-73`. `setup_parser` iterates it and registers one argparse sub-parser per
key, resolving the implementing module as `data.get('module_name', 'rez.cli.%s' % subcommand)`
(`src/rez/cli/_main.py:111-117`) — so the **dict key is both the `rez <key>` word and the module
filename stem**. That is why the hyphenated files work: `pkg-cache` → module `rez.cli.pkg-cache`
(`importlib.import_module` accepts non-identifier names, `src/rez/cli/_main.py:60-63`). Each module
must expose `setup_parser`, `command` and a module docstring whose **first line** becomes the help
blurb (`src/rez/cli/_main.py:36-58`).

Console scripts are generated from `src/rez/cli/_entry_points.py`: `get_specifications()` (`:15`)
walks the module for functions carrying `__scriptname__` and emits
`"<scriptname> = rez.cli._entry_points:<func>"` (`:15-40`, decorator `:43-47`); consumed by
`setup.py` as `entry_points={"console_scripts": get_specifications().values()}` (`setup.py:62-64`).
**`pyproject.toml` declares no entry points** — searched `pyproject.toml` for
`console_scripts|entry-points|entry_points`: no matches; `setup.py` is the only wiring.

**`rez-<name>` vs `rez <name>`:** all 31 subcommands are reachable as `rez <name>`; 29 additionally
get a `rez-<name>` console script. The two exceptions are the **hidden/internal** ones, which get
underscore-prefixed scripts and are not meant to be typed: `complete` → `_rez-complete`
(`src/rez/cli/_entry_points.py:81-85`) and `forward` → `_rez_fwd` (`:88-92`). Two further scripts take
no subcommand: `rez` (`:65`) and its macOS alias `rezolve` (`:72-78`).

**`depends` / `search`: both spellings exist.** `rez-depends`
(`src/rez/cli/_entry_points.py:130`) *and* `rez depends` (`src/rez/cli/_util.py:35`);
`rez-search` (`src/rez/cli/_entry_points.py:214`) *and* `rez search`
(`src/rez/cli/_util.py:57`). Neither is deprecated (§23).

**Deprecated / hidden commands.** `src/rez/deprecations.py` contains **no command deprecations**.
Two commands are hidden rather than deprecated: `complete` and `forward`, both flagged
`"hidden": True` in `subcommands` (`src/rez/cli/_util.py:31-33`, `:40-43`) and both setting
`__doc__ = argparse.SUPPRESS` (`src/rez/cli/complete.py:11`, `src/rez/cli/forward.py:10`), which
strips them from `--help` output (`src/rez/cli/_util.py:150-152`).

### 24.2 The commands

| Filename | CLI name(s) | Capability |
|---|---|---|
| `bind.py` | `rez-bind`, `rez bind` | Create a Rez package for existing software via a bind module (`src/rez/cli/bind.py:6`) |
| `build.py` | `rez-build`, `rez build` | Build a package from source (`:6`; `arg_mode: grouped`) |
| `config.py` | `rez-config`, `rez config` | Print current rez settings, or the list of config files searched/sourced (`:6`) |
| `context.py` | `rez-context`, `rez context` | Print information about the current rez context, or a given context file (`:6`) |
| `complete.py` | `rez complete` (+ hidden script `_rez-complete`) | Print shell completion strings; hidden (`src/rez/cli/complete.py:6`) |
| `cp.py` | `rez-cp`, `rez cp` | Copy a package from one repository to another (`:6`) |
| `depends.py` | **`rez-depends` and `rez depends`** | Perform a reverse package dependency lookup (`:6`) |
| `diff.py` | `rez-diff`, `rez diff` | Compare the source code of two packages (`:6`) |
| `env.py` | `rez-env`, `rez env` | Open a rez-configured shell, possibly interactive (`:6`; `arg_mode: grouped`) |
| `forward.py` | `rez forward` (+ hidden script `_rez_fwd`) | Internal target of generated forwarding scripts (`arg_mode: passthrough`) |
| `gui.py` | `rez-gui`, `rez gui` | Run the Rez GUI application (delegates to `rezgui.app.run`, `:25-26`) |
| `help.py` | `rez-help`, `rez help` | Display help for the given package, or open the Rez manual (`:6`) |
| `interpret.py` | `rez-interpret`, `rez interpret` | Execute some Rex code and print the interpreted result (`:6`) |
| `memcache.py` | `rez-memcache`, `rez memcache` | Manage and query memcache server(s) (`:6`) |
| `pip.py` | `rez-pip`, `rez pip` | Install a pip-compatible python package, and its dependencies, as rez packages (`:6`) |
| `pkg-cache.py` | `rez-pkg-cache`, `rez pkg-cache` | Manipulate a package cache (`:6`) |
| `pkg-ignore.py` | `rez-pkg-ignore`, `rez pkg-ignore` | Disable a package so it is hidden from resolves (`:6`) |
| `plugins.py` | `rez-plugins`, `rez plugins` | Get a list of a **package's** plugins (`:6`) |
| `python.py` | `rez-python`, `rez python` | Start a python interpreter or run a script within Rez's own execution context (`:6`; `arg_mode: passthrough`) |
| `release.py` | `rez-release`, `rez release` | Build a package from source and deploy it (`:6`; `arg_mode: grouped`) |
| `search.py` | **`rez-search` and `rez search`** | Search for packages (`:6`) |
| `selftest.py` | `rez-selftest`, `rez selftest` | Run unit tests; uses pytest if available (`:6`; `arg_mode: grouped`) |
| `status.py` | `rez-status`, `rez status` | Report current status of the environment, or of a tool/package/context/suite (`:6`) |
| `suite.py` | `rez-suite`, `rez suite` | Manage a suite or print information about an existing suite (`:6`) |
| `test.py` | `rez-test`, `rez test` | Run tests listed in a package's definition file (`:6`; `arg_mode: grouped`) |
| `view.py` | `rez-view`, `rez view` | View the contents of a package (`:6`) |
| `yaml2py.py` | `rez-yaml2py`, `rez yaml2py` | Print a `package.yaml` file in `package.py` format (`:6`) |
| `bundle.py` | `rez-bundle`, `rez bundle` | Bundle a context and its packages into a relocatable directory (`:6`) |
| `benchmark.py` | `rez-benchmark`, `rez benchmark` | Run a benchmarking suite for runtime resolves (`:6`) |
| `mv.py` | `rez-mv`, `rez mv` | Move a package from one repository to another (`:6`) |
| `rm.py` | `rez-rm`, `rez rm` | Remove package(s) from a repository (`:6`) |

Non-subcommand scripts: `rez` (`src/rez/cli/_entry_points.py:65`) and `rezolve`, an alias for macOS
where `rez` is a different tool (`:72-78`). All 33 scripts call `check_production_install()` first,
which warns on pip-based installs (`:50-60`).

---

# F. Prebuilt-binary packages

## 25. A standard "download a prebuilt binary and install it" mechanism

**There is no dedicated prebuilt-binary mechanism in Rez 3.4.0.** What exists is:

1. **The `custom` build system + `build_command` attribute** (§A.1.5) — a package may declare an
   arbitrary command, and that command may do anything, including fetch and unpack a tarball. Rez
   neither helps nor verifies.
2. **Upstream's own framing agrees:** the block of schema that declares `build_system` and
   `build_command` is literally commented as pre-built-package attributes:

```python
# src/rez/package_maker.py:86-89
# attributes specific to pre-built packages
Optional("build_system"):           str,
Optional("build_command"):          Or([str], str, False),
Optional("preprocess"):             _function_schema,
```

3. **The in-tree example is exactly a prebuilt-payload install**, with no build step at all —
   `example_packages/hello_world/package.py:24`:

```python
build_command = 'python {root}/build.py {install}'
```

   and `example_packages/hello_world/build.py` copies already-built `bin/` and `python/` trees into
   the install path (`:34-49`), reading the paths from the Rez build env vars at `:52-58`:

```python
# example_packages/hello_world/build.py:52-58
if __name__ == '__main__':
    build(
        source_path=os.environ['REZ_BUILD_SOURCE_PATH'],
        build_path=os.environ['REZ_BUILD_PATH'],
        install_path=os.environ['REZ_BUILD_INSTALL_PATH'],
        targets=sys.argv[1:]
    )
```

   Note the `targets` idiom: the script keys off the `{install}` placeholder (`"install" in (targets
   or [])`, `:48-49`), which is the documented `build_command` expansion
   (`src/rezplugins/build_system/custom.py:157`).

4. **`rez bind`** is the other prebuilt-facing path — it packages software *already on the system*
   (§E.23) — and **`rez pip`** is the third, for python distributions (§E.23). Neither downloads
   arbitrary binaries via a Rez-specified mechanism.

**No download facility exists in Rez's build or install path.**
`ABSENT — searched: grep -rn "urlretrieve\|urlopen\|requests\.\|urllib\|def download\|wget\|curl "
src/rez/ src/rezplugins/ --include=*.py`, filtered to exclude `src/rez/vendor/`. The only surviving
hits are unrelated:

* `src/rez/utils/amqp.py:11`, `:165` — `urllib.parse.urlsplit`, used to parse an AMQP broker URL for
  the `amqp` release hook. Not a download.
* `src/rez/utils/memcached.py:72` — the string "requests" in a docstring about server health.
* Identifier collisions in `src/rez/solver.py` and `src/rez/rex.py` on the substrings `requests` /
  `requested` (e.g. `src/rez/solver.py:1308`, `src/rez/resolved_context.py:165`), i.e. *package
  requests*, not HTTP requests.

**No checksum / hash verification facility exists in Rez's build or install path.**
`ABSENT — searched: grep -rn "sha256\|md5\|checksum\|verify_checksum\|hashlib" src/rez/
src/rezplugins/ --include=*.py`, excluding `src/rez/vendor/`. Every hit is a *hash for identity,
layout or cache-keying* — none is an integrity check:

| Hit | Purpose |
|---|---|
| `src/rez/cli/release.py:87` | `sha1` of the working dir, to name the temp release-message file (`:89-91`). |
| `src/rez/package_cache.py:11` | `sha1` for the package-cache directory layout (`:1041`, `:1000`). |
| `src/rez/package_filter.py:12`, `:83-91` | `sha1` of `str(self)` — a filter identity, used as a resolve-cache key (`src/rez/resolver.py:115`). |
| `src/rez/package_order.py:8` | `sha1` orderer identity, likewise a resolve-cache key (`src/rez/resolver.py:107`). |
| `src/rez/package_resources.py:23`, `:497-500` | `sha1` for **hashed variant subpaths** — a path-layout device (§A.4.2), explicitly documented as such at `docs/source/variants.rst:69-90`. |
| `src/rez/resolver.py:17` | `sha1` for memoization keys. |
| `src/rez/utils/memcached.py:15`, `:189` | `md5` for memcached key hashing (`md5(key.encode("utf-8")).hexdigest()`). |
| `src/rez/utils/sourcecode.py:313`, `:334` | `sha1` of an `@include` module's source. |
| `src/rezplugins/build_process/local.py:26`, `:325` | `sha1` of an `@include` module's source. |

**The one hash that is written to disk is not a verification.** During install, Rez writes a
`<module>.sha1` sidecar next to each `@include` module
(`src/rezplugins/build_process/local.py:325-332`). It *is* read back later
(`src/rez/utils/sourcecode.py:339-344`) — but only to serve as a **cache key** into the in-memory
module dict:

```python
# src/rez/utils/sourcecode.py:357-365
module = self.modules.get(hash_str)
if module is not None:
    return module
...
module = load_module_from_file(name, filepath)
self.modules[hash_str] = module
```

The stored hash is **never** compared against a freshly computed hash of the file it describes. It is
content-addressing for a cache, not integrity verification.

So: a re-specification that adds artifact checksums, signature verification, or a download step is
**adding** capability, not porting it.

## 26. Artifact provenance metadata as a package-level concept

**ABSENT as a specified package-level concept.**
`ABSENT — searched: grep -rni "provenance\|source_url\|upstream_revision\|license"
src/rez/package_resources.py src/rez/package_maker.py src/rez/package_serialise.py`. The only hits are
the `SPDX-License-Identifier` file headers (e.g. `src/rez/package_resources.py:1`). There is no
`license`, no `source_url`, no `upstream_revision`, no `homepage` field in any package schema.

**What Rez does specify that is adjacent** — all of it *release* provenance, not *artifact* provenance:

| Attribute | Location | Notes |
|---|---|---|
| `revision` | `src/rez/package_resources.py:165` | `Optional('revision'): object` — deliberately untyped, because its shape is VCS-plugin-specific (`src/rez/release_vcs.py:150-154`). For git it is a dict with `commit`, `branch`, `tracking_branch`, `fetch_url`, `push_url` (`src/rezplugins/release_vcs/git.py:166-200`). |
| `previous_revision` | `:169` | Same untyped convention. |
| `previous_version` | `:168` | `Version`. |
| `changelog` | `:166` | `str`; truncated to `config.max_package_changelog_chars` (`src/rez/build_process.py:440-442`). |
| `release_message` | `:167` | `Or(None, str)`. |
| `vcs` | `:170` | `str` — **just the VCS plugin name**, e.g. `"git"` (`src/rez/build_process.py:444`). Not a URL. |
| `authors` | `:129` | `[str]`. |
| `uuid` | `:141` | `str`; used to stop unrelated same-named packages being released as one (`src/rez/build_process.py:331-337`). |

All seven release-time attributes are grouped in `package_release_keys` —
`src/rez/package_resources.py:32-39`.

**Ad-hoc provenance is possible but unspecified.** The package schema ends with a catch-all:

```python
# src/rez/package_resources.py:173
Optional(str):               late_bound(object)
```

so any attribute name is accepted. `rez pip` exploits exactly this to record provenance on
pip-derived packages — `from_pip`, `pip_name`, `is_pure_python`
(`src/rez/pip.py:438-440`) plus `help`/`authors` from distribution metadata (`:442-462`). These are
conventions of one plugin, **not** part of the specification; nothing validates or consumes them
generically.

## 27. Rez-native reproducible / deterministic builds

**ABSENT.** There is no concept of reproducible or deterministic *builds* in Rez 3.4.0.

`ABSENT — searched: grep -rni "SOURCE_DATE_EPOCH\|deterministic\|reproducible" src/ docs/
--include=*.py --include=*.rst --include=*.md`, excluding `vendor/`. Every hit is about **solve**
determinism or unrelated prose:

* `src/rez/solver.py:57` — "Solves are deterministic - given a known request and set of package
  repositories…".
* `src/rez/solver.py:753` — "the sort is necessary to ensure solves are deterministic".
* `src/rez/solver.py:1462` — "rez solves must be deterministic, so this is why we sort."
* `src/rez/util.py:206` — invalid variant indices "are sorted for deterministic error messages"
  (implementation `src/rez/util.py:213`).
* `src/rez/tests/test_util.py:79` — a test docstring about deterministic error messages.
* `docs/source/variants.rst:228` — "A resolve is still deterministic."
* `docs/source/guides/linking_to_rez_documentation.rst:65` — "reproducible documentation" (about
  docs builds, not packages).

Specifically absent:

1. **No fixed/overridable build timestamp in the reproducible-builds sense.** `timestamp` is
   `int(time.time())` at install time (`src/rezplugins/package_repository/filesystem.py:1435`, §A.9).
   It can be pinned only by the `overrides` dict on a *new* package
   (`filesystem.py:1423-1431`) — there is no `SOURCE_DATE_EPOCH` support and no `REZ_TIMESTAMP` env
   var.
2. **No deterministic payload ordering.** The build product is whatever the build system wrote;
   Rez copies it wholesale and records no manifest, no file list, and no per-file hashes
   (`src/rezplugins/build_process/local.py:283-305`, `:256-305`). The only per-file hash Rez writes is
   the `@include` sidecar described in §F.25, and it is a cache key.
3. **No build-input pinning beyond the resolve.** A build's inputs are captured only as the resolved
   context saved to `build.rxt` (`src/rezplugins/build_process/local.py:294-295`) and copied into the
   variant install dir (`:297-298`), plus `variant.json` (`:252-262`). These are debug aids —
   `variant.json` is documented as "there for debugging purposes only" (`:248-251`).

**Summary for auditors:** Rez guarantees *resolve* determinism, not *build* determinism. Any
reproducible-build story in a re-specification is new surface.

---

## Quick-lookup index

Flat `concept → src/...:LINE` list for fast citation. Paths are relative to the clone root.

```
### Version / baseline
Rez version string                        -> src/rez/utils/_version.py:6

### A. Build — plugin contract
build_system plugin dir                   -> src/rezplugins/build_system/  (cmake.py, custom.py, make.py, rezconfig.py)
cmake plugin class                        -> src/rezplugins/build_system/cmake.py:32
cmake plugin name()                       -> src/rezplugins/build_system/cmake.py:67-69
cmake configure step                      -> src/rezplugins/build_system/cmake.py:136-149
cmake build step                          -> src/rezplugins/build_system/cmake.py:207-236
cmake install step                        -> src/rezplugins/build_system/cmake.py:238-249
custom plugin class                       -> src/rezplugins/build_system/custom.py:33
custom plugin build()                     -> src/rezplugins/build_system/custom.py:107-237
custom build_command expansion            -> src/rezplugins/build_system/custom.py:148-161
custom parse_build_args.py hook           -> src/rezplugins/build_system/custom.py:82-105
make plugin STUB (NotImplementedError)    -> src/rezplugins/build_system/make.py:24
cmake plugin defaults (rezconfig)         -> src/rezplugins/build_system/rezconfig.py:8-35

BuildSystem base class                    -> src/rez/build_system.py:126
BuildResult TypedDict                     -> src/rez/build_system.py:25-28
BuildSystem.name (abstract)               -> src/rez/build_system.py:129-132
BuildSystem.__init__                      -> src/rez/build_system.py:134-171
BuildSystem.is_valid_root (abstract)      -> src/rez/build_system.py:173-176
BuildSystem.child_build_system            -> src/rez/build_system.py:178-191
BuildSystem.bind_cli                      -> src/rez/build_system.py:193-203
BuildSystem.build (abstract, core)        -> src/rez/build_system.py:205-239
BuildSystem.set_standard_vars             -> src/rez/build_system.py:241-303
BuildSystem.add_pre_build_commands        -> src/rez/build_system.py:305-340
BuildSystem.add_standard_build_actions    -> src/rez/build_system.py:342-358

get_buildsys_types()                      -> src/rez/build_system.py:31-34
get_valid_build_systems()                 -> src/rez/build_system.py:37-86
  build_command beats build_system        -> src/rez/build_system.py:62-65
  detection + child subtraction           -> src/rez/build_system.py:72-86
create_build_system()                     -> src/rez/build_system.py:89-123

### A. Build — extension points
extend_path (namespace merging)           -> src/rez/plugin_managers.py:44
namespace example                         -> src/rezplugins/command/__init__.py:5-6
load_plugins (both passes)                -> src/rez/plugin_managers.py:132-134
load_plugins_from_namespace               -> src/rez/plugin_managers.py:136-191
  custom paths win (reversed)             -> src/rez/plugin_managers.py:150-152
  skip _-prefixed / rezconfig             -> src/rez/plugin_managers.py:165-166
load_plugins_from_entry_points            -> src/rez/plugin_managers.py:193-214
  entry point group rez.plugins.<type>    -> src/rez/plugin_managers.py:194
register_plugin_module / register_plugin()-> src/rez/plugin_managers.py:234-247
load_config_from_plugin (rezconfig)       -> src/rez/plugin_managers.py:229-232
plugin config schema aggregation          -> src/rez/plugin_managers.py:288-293
RezPluginManager docstring (how-to)       -> src/rez/plugin_managers.py:300-352
plugin type registrations (7 types)       -> src/rez/plugin_managers.py:543-549
third-party plugin worked example         -> example_extensions/hello_cmd/rezplugins/command/world.py:33-41
example packaging                         -> example_extensions/hello_cmd/setup.py:8-15

### A. Build — package attributes
build_command schema                      -> src/rez/package_maker.py:88
build_system schema                       -> src/rez/package_maker.py:87
pre_build_commands (schema form)          -> src/rez/package_resources.py:160
pre_build_commands (POD form)             -> src/rez/package_maker.py:83
pre_build_commands (serialised form)      -> src/rez/package_serialise.py:99
package_build_only_keys (stripped)        -> src/rez/package_resources.py:42-48
package_rex_keys                          -> src/rez/package_resources.py:51-57
post_build_commands                       -> ABSENT (grep -rn "post_build_commands" src/)

### A. Build — env vars
REZ_BUILD_ENV                             -> src/rez/build_system.py:264
REZ_BUILD_PATH                            -> src/rez/build_system.py:265
REZ_BUILD_THREAD_COUNT                    -> src/rez/build_system.py:266
REZ_BUILD_VARIANT_INDEX                   -> src/rez/build_system.py:267
REZ_BUILD_VARIANT_REQUIRES                -> src/rez/build_system.py:268
REZ_BUILD_VARIANT_SUBPATH                 -> src/rez/build_system.py:269
REZ_BUILD_PROJECT_VERSION                 -> src/rez/build_system.py:270
REZ_BUILD_PROJECT_NAME                    -> src/rez/build_system.py:271
REZ_BUILD_PROJECT_DESCRIPTION             -> src/rez/build_system.py:272
REZ_BUILD_PROJECT_FILE                    -> src/rez/build_system.py:273
REZ_BUILD_SOURCE_PATH                     -> src/rez/build_system.py:274-278
REZ_BUILD_REQUIRES                        -> src/rez/build_system.py:279-283
REZ_BUILD_REQUIRES_UNVERSIONED            -> src/rez/build_system.py:284-288
REZ_BUILD_TYPE                            -> src/rez/build_system.py:289
REZ_BUILD_INSTALL                         -> src/rez/build_system.py:290
REZ_BUILD_INSTALL_PATH (conditional)      -> src/rez/build_system.py:293-294
REZ_IN_REZ_RELEASE (conditional, rez-1)   -> src/rez/build_system.py:296-299
BuildType enum (local=0, central=1)       -> src/rez/build_process.py:77-80
build env var docs                        -> docs/source/environment.rst:135-204
build_thread_count config                 -> src/rez/rezconfig.py:793
build_directory config                    -> src/rez/rezconfig.py:783
REZ_<SETTING> env override mechanism      -> src/rez/config.py:87-89

### A. Build — variants
variants schema                           -> src/rez/package_resources.py:178-182
variant requires composition              -> src/rez/packages.py:429-431
_variant subpath (default + hashed)       -> src/rez/package_resources.py:493-521
  hashed = sha1 hexdigest                 -> src/rez/package_resources.py:497-500
  default = join of safe_str() reqs       -> src/rez/package_resources.py:518-521
VariantResource.subpath property          -> src/rez/package_resources.py:371-379
VariantResourceHelper._root               -> src/rez/package_resources.py:523-529
Variant._non_shortlinked_subpath          -> src/rez/packages.py:486-488
hashed_variants attribute                 -> src/rez/package_resources.py:147
platform/arch/os variant convention       -> docs/source/variants.rst:106-124
variant disk layout example               -> docs/source/variants.rst:53-56
variant_shortlinks_dirname config         -> src/rez/rezconfig.py:816
use_variant_shortlinks docs               -> src/rez/rezconfig.py:818-821
shortlink creation during install         -> src/rezplugins/build_process/local.py:193-218
resolve_variant_indices (negatives)       -> src/rez/util.py:195-215
visit_variants                            -> src/rez/build_process.py:210-239
variant build/install path computation    -> src/rezplugins/build_process/local.py:157-166
subpath formatting in utils/formatting.py -> ABSENT (read outline; no subpath symbol)

### A. Build — requires
requires / build_requires / private_build_requires -> src/rez/package_resources.py:131-134
Variant.get_requires()                    -> src/rez/packages.py:433-452
build context uses all three              -> src/rez/build_process.py:259-260
build_requires NOT stripped on install    -> src/rez/package_resources.py:42-48

### A. Build — CLI
rez build setup_parser                    -> src/rez/cli/build.py:87-110
  -c/--clean                              -> src/rez/cli/build.py:88-90
  -i/--install                            -> src/rez/cli/build.py:91-94
  -p/--prefix                             -> src/rez/cli/build.py:95-97
  --fail-graph                            -> src/rez/cli/build.py:98-101
  -s/--scripts                            -> src/rez/cli/build.py:102-106
  --view-pre                              -> src/rez/cli/build.py:107-109
setup_parser_common (shared w/ release)   -> src/rez/cli/build.py:35-84
  --process                               -> src/rez/cli/build.py:43-46
  -b/--build-system                       -> src/rez/cli/build.py:67-71
  --variants                              -> src/rez/cli/build.py:73-76
  --ba/--build-args                       -> src/rez/cli/build.py:77-80
  --cba/--child-build-args                -> src/rez/cli/build.py:81-84
rez build --release / --paths / --keep-tmp / --extra-packages / --view-post -> ABSENT (see §A.6.3)

### A. Build — process model
BuildProcess base                         -> src/rez/build_process.py:83
BuildProcess.build (abstract)             -> src/rez/build_process.py:147-169
BuildProcess.release (abstract)           -> src/rez/build_process.py:171-188
BuildProcessHelper                        -> src/rez/build_process.py:199
create_build_process()                    -> src/rez/build_process.py:42-74
LocalBuildProcess.build()                 -> src/rezplugins/build_process/local.py:60-88
_build_variant_base (the step sequence)   -> src/rezplugins/build_process/local.py:149-305
  pre_variant_install                     -> src/rezplugins/build_process/local.py:186-189
  variant re-evaluation (building=True)   -> src/rezplugins/build_process/local.py:220-234
  create_build_context + build.rxt        -> src/rezplugins/build_process/local.py:237-240
  build_system.build() invocation         -> src/rezplugins/build_process/local.py:264-274
  failure -> rmtree + BuildError          -> src/rezplugins/build_process/local.py:276-281
  extra files + include modules           -> src/rezplugins/build_process/local.py:283-305
_build_variant (tests, variant.install)   -> src/rezplugins/build_process/local.py:340-392
BuildStep enum/objects                    -> ABSENT (grep -rn "BuildStep" src/ docs/)

### A. Build — remote
remote build process STUB                 -> src/rezplugins/build_process/remote.py:21, :24
remote register_plugin                    -> src/rezplugins/build_process/remote.py:27-28
"only local available" config comment     -> src/rez/rezconfig.py:824-825
default_build_process config              -> src/rez/rezconfig.py:828

### A. Build — timestamp
timestamp written on install              -> src/rezplugins/package_repository/filesystem.py:1433-1435
timestamp schema                          -> src/rez/package_resources.py:164
package_release_keys                      -> src/rez/package_resources.py:32-39
overrides precedence (new vs existing pkg)-> src/rezplugins/package_repository/filesystem.py:1423-1431
Variant.install(overrides=...)            -> src/rez/packages.py:454-484
PackageRepository.remove sentinel         -> src/rez/package_repository.py:79
rez-1 release_time.txt migration          -> src/rezplugins/package_repository/filesystem.py:233-238
build_time field                          -> ABSENT (grep -rn "build_time" src/; only vendored distlib)

### B. Test
rez test setup_parser                     -> src/rez/cli/test.py:11-44
  --dry-run                               -> src/rez/cli/test.py:15-18
  --stop-on-fail                          -> src/rez/cli/test.py:19-21
  --inplace                               -> src/rez/cli/test.py:22-25
  --extra-packages                        -> src/rez/cli/test.py:26-28
  --paths                                 -> src/rez/cli/test.py:29-31
  --no-local                              -> src/rez/cli/test.py:32-34
rez test --no-safe / --clean              -> ABSENT (see §B.10)
PackageTestRunner                         -> src/rez/package_test.py:22
PackageTestRunner docstring (tests dict)  -> src/rez/package_test.py:22-51
PackageTestRunner.__init__                -> src/rez/package_test.py:52-103
  common timestamp across tests           -> src/rez/package_test.py:101-103
get_package_test_names (run_on filter)    -> src/rez/package_test.py:141-193
run_test (exit-code semantics)            -> src/rez/package_test.py:252-502
  non-zero => failed, first propagated    -> src/rez/package_test.py:472-489
  dry-run => skipped                      -> src/rez/package_test.py:439-446
pre_test_commands execution               -> src/rez/package_test.py:448-462
_get_test_info                            -> src/rez/package_test.py:542-584
_get_context (testing=True, caching)      -> src/rez/package_test.py:586-634
PackageTestResults                        -> src/rez/package_test.py:677
rez:setup / rez:test / rez:teardown       -> ABSENT (grep -rn "rez:setup\|rez:test\|rez:teardown" .)
pytest/unittest framework detection       -> ABSENT (only docstring example src/rez/package_test.py:32)
tests schema                              -> src/rez/package_resources.py:101-121
tests attribute binding                   -> src/rez/package_resources.py:154
_run_tests (post-install tests)           -> src/rezplugins/build_process/local.py:449-519
  pre_install trigger (rez build)         -> src/rezplugins/build_process/local.py:374-379
  pre_release trigger (rez release)       -> src/rezplugins/build_process/local.py:428-433
  _redirected_base temp repo trick        -> src/rezplugins/build_process/local.py:484-489
  failure => PackageTestError             -> src/rezplugins/build_process/local.py:514-519
REZ_TEST_* env vars                       -> ABSENT (grep -rn "REZ_TEST" src/)

### C. Release
rez release setup_parser                  -> src/rez/cli/release.py:15-42
  -m/--message                            -> src/rez/cli/release.py:20-22
  --vcs                                   -> src/rez/cli/release.py:23-25
  --no-latest                             -> src/rez/cli/release.py:26-28
  --ignore-existing-tag                   -> src/rez/cli/release.py:29-33
  --skip-repo-errors                      -> src/rez/cli/release.py:34-38
  --no-message                            -> src/rez/cli/release.py:39-41
rez release --dry-run                     -> ABSENT (API-only: src/rez/packages.py:454-467)
release message prompting                 -> src/rez/cli/release.py:82-140
prompt_release_message config             -> src/rez/rezconfig.py:804

release phases (LocalBuildProcess.release)-> src/rezplugins/build_process/local.py:90-147
  pre_release validation                  -> src/rez/build_process.py:301-347
    release path exists                   -> src/rez/build_process.py:304-307
    vcs.validate_repostate                -> src/rez/build_process.py:310-313
    existing-tag check                    -> src/rez/build_process.py:315-326
    UUID mismatch check                   -> src/rez/build_process.py:328-337
    ensure_latest check                   -> src/rez/build_process.py:339-347
  get_release_data                        -> src/rez/build_process.py:414-448
  run_hooks(pre_release)                  -> src/rezplugins/build_process/local.py:103-109
  _release_variant                        -> src/rezplugins/build_process/local.py:394-447
  run_hooks(post_release)                 -> src/rezplugins/build_process/local.py:122-128
  post_release (tag)                      -> src/rez/build_process.py:349-357
repo_operation (error swallowing)         -> src/rez/build_process.py:202-208

release_vcs plugins                       -> src/rezplugins/release_vcs/ (git.py, hg.py, svn.py, stub.py)
GitReleaseVCS                             -> src/rezplugins/release_vcs/git.py:21
HgReleaseVCS                              -> src/rezplugins/release_vcs/hg.py:18
SvnReleaseVCS                             -> src/rezplugins/release_vcs/svn.py:60
StubReleaseVCS                            -> src/rezplugins/release_vcs/stub.py:16
create_release_vcs (closest root wins)    -> src/rez/release_vcs.py:23-69
ReleaseVCS base                           -> src/rez/release_vcs.py:72
  name (abstract)                         -> src/rez/release_vcs.py:91-94
  is_valid_root (abstract)                -> src/rez/release_vcs.py:104-113
  search_parents_for_root (abstract)      -> src/rez/release_vcs.py:115-120
  validate_repostate (abstract)           -> src/rez/release_vcs.py:142-144
  get_current_revision (abstract)         -> src/rez/release_vcs.py:146-155
  get_changelog (abstract)                -> src/rez/release_vcs.py:157-172
  tag_exists (abstract)                   -> src/rez/release_vcs.py:174-183
  create_release_tag (abstract)           -> src/rez/release_vcs.py:185-195
  export (abstract)                       -> src/rez/release_vcs.py:197-209
git validate_repostate                    -> src/rezplugins/release_vcs/git.py:93-142
git get_current_revision                  -> src/rezplugins/release_vcs/git.py:166-200
git get_changelog                         -> src/rezplugins/release_vcs/git.py:144-164

tag_name config (default {qualified_name}) -> src/rezplugins/release_vcs/rezconfig.py:12
tag_name docstring / warning              -> src/rezplugins/release_vcs/rezconfig.py:5-11
check_tag config (default False)          -> src/rezplugins/release_vcs/rezconfig.py:42
releasable_branches config                -> src/rezplugins/release_vcs/rezconfig.py:14-19
git allow_no_upstream                     -> src/rezplugins/release_vcs/rezconfig.py:44-47
get_current_tag_name()                    -> src/rez/build_process.py:359-367
tag_exists (git)                          -> src/rezplugins/release_vcs/git.py:202-204
create_release_tag no-op if exists (git)  -> src/rezplugins/release_vcs/git.py:206-208
create_release_tag no-op if exists (stub) -> src/rezplugins/release_vcs/stub.py:62-64

release_hook plugins                      -> src/rezplugins/release_hook/ (amqp.py, command.py, emailer.py)
AmqpReleaseHook                           -> src/rezplugins/release_hook/amqp.py:17
CommandReleaseHook                        -> src/rezplugins/release_hook/command.py:24
EmailReleaseHook                          -> src/rezplugins/release_hook/emailer.py:19
ReleaseHook base                          -> src/rez/release_hook.py:39
  name (abstract)                         -> src/rez/release_hook.py:46-49
  __init__ (reads own settings)           -> src/rez/release_hook.py:51-60
  pre_build                               -> src/rez/release_hook.py:62-84
  pre_release                             -> src/rez/release_hook.py:86-110
  post_release                            -> src/rez/release_hook.py:112-131
ReleaseHookEvent enum                     -> src/rez/release_hook.py:134-143
run_hooks                                 -> src/rez/build_process.py:369-388
release_hooks config                      -> src/rez/rezconfig.py:800

release_message schema                    -> src/rez/package_resources.py:167
release_packages_path config              -> src/rez/rezconfig.py:73
local_packages_path config                -> src/rez/rezconfig.py:69
packages_path config                      -> src/rez/rezconfig.py:62-67
nonlocal_packages_path usage              -> src/rez/build_process.py:266-269

### D. Repository & distribution
package_repository plugins (only 2)       -> src/rezplugins/package_repository/ (filesystem.py, memory.py)
FileSystemPackageRepository               -> src/rezplugins/package_repository/filesystem.py:438
  name()                                  -> src/rezplugins/package_repository/filesystem.py:490-492
  resource classes                        -> .../filesystem.py:93, :140, :272, :288, :353, :416
  schema_dict                             -> .../filesystem.py:474-477
  register_plugin()                       -> .../filesystem.py:1545-1546
MemoryPackageRepository                   -> src/rezplugins/package_repository/memory.py:115
package_repository rezconfig              -> src/rezplugins/package_repository/rezconfig.py:5-47
get_package_repository_types()            -> src/rez/package_repository.py:26-28
PackageRepositoryGlobalStats              -> src/rez/package_repository.py:46
PackageRepository base                    -> src/rez/package_repository.py:69
  remove sentinel                         -> src/rez/package_repository.py:79
  name (abstract)                         -> src/rez/package_repository.py:82
  get_package_family (abstract)           -> src/rez/package_repository.py:143
  iter_package_families (abstract)        -> src/rez/package_repository.py:154
  iter_packages (abstract)                -> src/rez/package_repository.py:163
  iter_variants (abstract)                -> src/rez/package_repository.py:175
  ignore_package (abstract)               -> src/rez/package_repository.py:230
  unignore_package (abstract)             -> src/rez/package_repository.py:249
  remove_package (abstract)               -> src/rez/package_repository.py:262
  remove_package_family (abstract)        -> src/rez/package_repository.py:277
  remove_ignored_since (abstract)         -> src/rez/package_repository.py:289
  install_variant (abstract)              -> src/rez/package_repository.py:330-333
  get_package_payload_path (abstract)     -> src/rez/package_repository.py:499
PackageRepositoryManager                  -> src/rez/package_repository.py:526
  URI '@' split + filesystem default      -> src/rez/package_repository.py:562-576
  _get_repository                         -> src/rez/package_repository.py:652-656
package_repository_manager singleton      -> src/rez/package_repository.py:660
Package / Variant classes                 -> src/rez/packages.py:203 / :342
resource classes                          -> src/rez/package_resources.py:275, :315, :324, :346, :397, :470
'|' options separator in repo URIs        -> ABSENT (grep -rn "split('|')" src/rez/)

package_filter classes                    -> src/rez/package_filter.py:21, :97, :234, :333, :436, :455, :473, :491, :519
package_filter config key                 -> src/rez/config.py:535 (default src/rez/rezconfig.py:453)
package_order classes                     -> src/rez/package_order.py:53, :205, :243, :297, :415, :468, :635
get_orderer (default version descending)  -> src/rez/package_order.py:739-748
register_orderer                          -> src/rez/package_order.py:751-765
package_orderers config key               -> src/rez/config.py:536 (default src/rez/rezconfig.py:459)
package_order config key                  -> ABSENT (grep -rn '"package_order"' src/)
package_filter/order plugin types         -> ABSENT (grep -n "package_filter\|package_order" src/rez/plugin_managers.py)

rez cp flags                              -> src/rez/cli/cp.py:12-62
rez mv flags                              -> src/rez/cli/mv.py:12-27
rez rm flags                              -> src/rez/cli/rm.py:15-36
copy_package()                            -> src/rez/package_copy.py:31-44
  keep_timestamp injection                -> src/rez/package_copy.py:236-237
move_package() (copy + hide)              -> src/rez/package_move.py:13-14, :17-19, :56-85
remove_package_family()                   -> src/rez/package_remove.py:13
remove_package()                          -> src/rez/package_remove.py:31
remove_packages_ignored_since()           -> src/rez/package_remove.py:53-54

memcached_uri config                      -> src/rez/config.py:425 (default src/rez/rezconfig.py:170)
resolve_caching / cache_package_files / cache_listdir -> src/rez/config.py:493 / :494 / :495
resource_caching_maxsize                  -> src/rez/config.py:474
rez memcache flags                        -> src/rez/cli/memcache.py:12-29
memcached Client                          -> src/rez/utils/memcached.py:26
memcached() decorator                     -> src/rez/utils/memcached.py:272-273
pool_memcached_connections()              -> src/rez/utils/memcached.py:253
cache_packages_path config                -> src/rez/config.py:438 (default src/rez/rezconfig.py:268)
Resource / ResourceHandle / ResourcePool  -> src/rez/utils/resources.py:56 / :152 / :204
  LRU wiring                              -> src/rez/utils/resources.py:212-215
load_resource / CachedFile                -> ABSENT (grep -rn "load_resource\|CachedFile" src/)
PackageCache                              -> src/rez/package_cache.py:39
rez pkg-cache flags                       -> src/rez/cli/pkg-cache.py:16-68
package_cache_* config keys               -> src/rez/config.py:482-491

### E. Ecosystem surface
rez bind CLI                              -> src/rez/cli/bind.py:42
bind_package engine                       -> src/rez/package_bind.py:81
bind module exec (not import)             -> src/rez/package_bind.py:160-162
bind dependency recursion                 -> src/rez/package_bind.py:134-138
bind modules (src/rez/bind/)              -> arch:14, platform:14, os:14, python:40, rez:21, rezgui:35,
                                             pip:11, setuptools:11, sip:12, PyQt:12, PySide:11,
                                             cmake:25, gcc:25, hello_world:43, _pymodule.py:59
rez pip CLI                               -> src/rez/cli/pip.py:39
pip_install_package                       -> src/rez/pip.py:239
pip invoked as `python -m pip`            -> src/rez/pip.py:57
distlib DistributionPath enumeration      -> src/rez/pip.py:321-323
pip package make_package + hashed_variants-> src/rez/pip.py:406, :432-435
pip provenance attrs (from_pip, ...)      -> src/rez/pip.py:438-440
pip name/version translation              -> src/rez/utils/pip.py:44 / :46
rez env CLI                               -> src/rez/cli/env.py:147
rez env flags                             -> src/rez/cli/env.py:20-133 (table in §E.23)
rez env --suite/--create/--no-rez-env     -> ABSENT (see §E.23)
rez context CLI                           -> src/rez/cli/context.py:112
ResolvedContext to_dict / from_dict       -> src/rez/resolved_context.py:1604 / :1704
context save / load                       -> src/rez/resolved_context.py:724 / :766
context format sniff (json vs yaml)       -> src/rez/resolved_context.py:2043-2047
rez suite CLI                             -> src/rez/cli/suite.py:89
Suite class                               -> src/rez/suite.py:48
Suite.save (suite.yaml)                   -> src/rez/suite.py:477
Suite.load                                -> src/rez/suite.py:517-521
suite tool wrapper generation             -> src/rez/suite.py:509-515
suite tool invocation entry               -> src/rez/suite.py:787
SuiteVisibility enum                      -> src/rez/resolved_context.py:82
suite_visibility config                   -> src/rez/config.py:434
`.rez` suite file                         -> ABSENT (suite.yaml only)
shell plugins                             -> src/rezplugins/shell/ (sh:23, bash:18, zsh:22, csh:25,
                                             tcsh:18, cmd:22, powershell:11, pwsh:11, gitbash:23)
Shell base class                          -> src/rez/shells.py:74
  schema_dict                             -> src/rez/shells.py:77
  name / file_extension / get_syspaths    -> src/rez/shells.py:79 / :113 / :139
  startup_capabilities / spawn_shell      -> src/rez/shells.py:122 / :213
  join (concrete default)                 -> src/rez/shells.py:314
UnixShell base                            -> src/rez/shells.py:344
ActionInterpreter (env verb contract)     -> src/rez/rex.py:454
  setenv / unsetenv / resetenv            -> src/rez/rex.py:501 / :504 / :507
  prependenv / appendenv                  -> src/rez/rex.py:510 / :515
  alias / source / command / shebang      -> src/rez/rex.py:520 / :535 / :529 / :538
  escape_string (no-op default)           -> src/rez/rex.py:546, :566
get_shell_types / create_shell            -> src/rez/shells.py:32 / :58
get_rezenv_*                              -> ABSENT (grep -rn "get_rezenv" src/)
rez yaml2py                               -> src/rez/cli/yaml2py.py:18
rez plugins                               -> src/rez/cli/plugins.py:24
rez-depends                               -> src/rez/cli/depends.py:45 (entry point _entry_points.py:130)
rez-search                                -> src/rez/cli/search.py:69 (entry point _entry_points.py:214)
rez config                                -> src/rez/cli/config.py:33
  --search-list / --source-list           -> src/rez/cli/config.py:18 / :22
  --list / --plugins / --plugin-config-data / --validate-config-file -> ABSENT
rez status                                -> src/rez/cli/status.py:26
Status class                              -> src/rez/status.py:23
rez help                                  -> src/rez/cli/help.py:28
PackageHelp                               -> src/rez/package_help.py:20

### E. Command surface
subcommand registry                       -> src/rez/cli/_util.py:24-73
subcommand -> module mapping               -> src/rez/cli/_main.py:111-117
rez foo / rez-foo equivalence             -> src/rez/cli/_main.py:130-137
console_scripts generation                -> src/rez/cli/_entry_points.py:15-40
console_scripts wiring (setup.py only)    -> setup.py:62-64
pyproject.toml entry points               -> ABSENT (searched pyproject.toml)
deprecated commands                       -> ABSENT (src/rez/deprecations.py: config-only, :9 / :36)

### F. Prebuilt / provenance / reproducibility
prebuilt-binary mechanism                 -> custom build system + build_command:
                                             src/rezplugins/build_system/custom.py:33, :107-237
"pre-built packages" schema comment       -> src/rez/package_maker.py:86
prebuilt example package                  -> example_packages/hello_world/package.py:24
prebuilt example build script             -> example_packages/hello_world/build.py:34-58
download facility (urlretrieve/urlopen)   -> ABSENT (grep -rn "urlretrieve\|urlopen\|requests\." src/rez/ src/rezplugins/)
checksum / sha256 / verify                -> ABSENT (grep -rn "sha256\|md5\|checksum\|hashlib" src/rez/ src/rezplugins/)
@include .sha1 sidecar = cache key only   -> src/rezplugins/build_process/local.py:325-332 (written)
                                             src/rez/utils/sourcecode.py:339-344, :357-365 (read as cache key)
artifact provenance (source_url, license) -> ABSENT (grep -rni "provenance\|source_url\|license" package_resources.py
                                             package_maker.py package_serialise.py)
release provenance (revision, changelog)  -> src/rez/package_resources.py:32-39, :165-170
ad-hoc provenance (rez pip)               -> src/rez/pip.py:438-440 (via catch-all src/rez/package_resources.py:173)
SOURCE_DATE_EPOCH / reproducible builds   -> ABSENT (grep -rni "SOURCE_DATE_EPOCH\|deterministic\|reproducible" src/ docs/)
solve determinism (not build determinism) -> src/rez/solver.py:57, :753, :1462
```
