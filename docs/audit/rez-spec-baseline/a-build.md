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
def __init__(
    self,
    working_dir,
    opts=None,
    package=None,
    write_build_scripts: bool = False,
    verbose: bool = False,
    build_args=[],
    child_build_args=[],
) -> None:
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
        cls = plugin_manager.get_plugin_class("build_system", buildsys_name)
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
    """Enum to represent the type of build."""

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
package_schema_dict.update(
    {
        # deliberately not possible to late bind
        Optional("variants"): [[PackageRequest]]
    }
)
```

i.e. `list[list[PackageRequest]]`. Equivalent POD entry: `src/rez/package_resources.py:230-231`
(note the identical "deliberately not possible to late bind" comment at `:230`). Serialised form:
`src/rez/package_serialise.py:89`. Maker form: `src/rez/package_maker.py:65-66`, again with the same
comment at `:65`.

`variant_requires` is **not** a package attribute — it is derived. For a `Variant`, `requires` is
the parent package's `requires` plus the variant's own entry:

```python
# src/rez/packages.py:429-431
return (self.parent.requires or []) + self.variant_requires
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
        ...  # shortlink lookup, :502-515
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
    ["platform-linux", "arch-x86_64", "os-Ubuntu-16.04"],
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
request = variant.get_requires(build_requires=True, private_build_requires=True)
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
    "pre_build_commands",
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

