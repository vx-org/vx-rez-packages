# Build dimension audit — rez-next vs upstream Rez

Scope: rez-next's **build** dimension (build_system plugin family, plugin registration protocol, build commands, build-time environment, variants, build requirements, `rez build` CLI, build process model, remote build, build timestamps, `install_variant` / variant-URI lookup) measured against the upstream Rez specification.

## Audit basis

| Side | Artifact | Identifier |
|---|---|---|
| rez-next | git checkout under `rez-next/` | commit `97eef03928012d540f45d25fa82553da123e8786` (2026-10-10), release `0.3.10` (`.release-please-manifest.json`) |
| upstream Rez | local installation | `rez 3.4.0` installed from PyPI (`rez` + `rezplugins`, same wheel); version confirmed at `rez/utils/_version.py:5` |
| upstream Rez | source cross-check | `https://github.com/AcademySoftwareFoundation/rez` (default branch `main`) — `nerdvegas/rez` now redirects here and uses a `src/` layout |

Commands that produced upstream evidence (all read-only):

```console
$ ls <site-packages>/rezplugins/build_system/
__init__.py  cmake.py  cmake_files  custom.py  make.py  rezconfig.py  template_files

$ ls <site-packages>/rezplugins/build_process/
__init__.py  local.py  remote.py  rezconfig.py

$ curl -sSL https://api.github.com/repos/AcademySoftwareFoundation/rez/contents/src/rezplugins/build_system
# -> __init__.py, cmake.py, cmake_files, custom.py, make.py, rezconfig.py, template_files
```

Every upstream claim below is backed by a `file:line` in the local 3.4.0 install. Where I could not verify something authoritatively, the entry says `upstream-side: UNVERIFIED (reason)`.

Path convention in this document: `rez-next/…` = the rez-next checkout; `<SP>/rez/…` = the upstream package.

---

## 1. build_system plugin family

### rez-next: 8 built-in systems

Declared in `rez-next/crates/rez-next-build/src/systems/mod.rs:14-31` and registered in both the enum `BuildSystemType` (`:43-62`) and `get_buildsys_types()` (`:82-93`):

```rust
// crates/rez-next-build/src/systems/mod.rs:82-93
pub fn get_buildsys_types() -> Vec<&'static str> {
    vec!["cmake", "make", "python", "nodejs", "cargo", "binary_archive", "pypi", "custom"]
}
```

All eight are real, compilable Rust types dispatched through `BuildSystem::{configure,compile,test,package,install}` (`systems/mod.rs:202-301`). This is **not** a plugin registry — it is a closed Rust `enum`, so the set is fixed at compile time.

| System | Implementation | Behaviour (steps: configure / compile / test / package / install) | `package.py` fields read |
|---|---|---|---|
| `cmake` | `systems/cmake.rs` | `cmake -S <src> -B <build_dir> -DCMAKE_INSTALL_PREFIX=<install> -DCMAKE_BUILD_TYPE=(Release\|Debug) <build_args>` (`cmake.rs:27-41`) / `cmake --build <build_dir> [--config Release]` (`:67-74`) / `ctest --output-on-failure` (`:104`) / no-op (`:116-128`) / `cmake --install .` run with cwd = build dir (`:141`) | `build_system = "cmake"`; plus CLI `--build-args` → `BuildOptions.build_args` and `--release` → `BuildOptions.release_mode` (`cmake.rs:35-41`) |
| `make` | `systems/make.rs` | no-op (`:20-32`) / `make` (`:44`) / `make test` (`:66`) / no-op (`:78-90`) / `make install DESTDIR="<install>"` via `cmd_builder::make_install_cmd` (`:102`, `cmd_builder.rs:73-75`) | `build_system = "make"`. Ignores `build_args` and `release_mode` entirely |
| `python` | `systems/python.rs` | if `rezbuild.py` exists, probe `python --version` and discard the result (`:26-33`) / `rezbuild.py` → `python <script> build <build_dir> <install_dir>` (`:57-62`); elif `setup.py` → `python setup.py build --build-base <build_dir>` (`:75-78`); elif `pyproject.toml` → `pip wheel . -w <build_dir> --no-deps` (`:91-94`); else skip (`:105-111`) / `python -m pytest` then `python -m unittest discover` (`:125-143`) / no-op (`:146-158`) / `rezbuild.py` → `python <script> install <build_dir> <install_dir>` (`:177-182`); elif `setup.py` → `python setup.py install --prefix <install>` (`:194-197`); elif `pyproject.toml` → `pip install . --target <install> --no-deps` (`:209-212`); else `copy_package_files` (`:224-225`) | `build_system = "python"`; presence of `rezbuild.py` / `setup.py` / `pyproject.toml` on disk |
| `nodejs` | `systems/nodejs.rs` | `npm install` (`:29`) / `npm run build` (optional, non-fatal) (`:50-57`) / `npm test` (optional) (`:70-77`) / no-op (`:80-92`) / copy `dist/` if present else the whole source dir into install (`:104-110`) | `build_system = "nodejs"` |
| `cargo` | `systems/cargo_build.rs` | `cargo check` (`:29`) / `cargo build [--release]` (`:41-46`) / `cargo test` (`:67`) / `cargo package --no-verify` (optional) (`:79-86`) / `cargo install --path . [--release] --root <install>` (`:106-112`) | `build_system = "cargo"`; `--release` |
| `binary_archive` | `systems/binary_archive.rs` | no-op / no-op / no-op / no-op / download-or-reuse archive, verify SHA-256, extract, strip payload prefix, copy into install root (`:99-147`) | `build_system = "binary_archive"`; **no package.py fields** — driven purely by env vars `REZ_BINARY_ARCHIVE_ARTIFACT`, `REZ_BINARY_ARCHIVE_URL`, `REZ_BINARY_ARCHIVE_SHA256`, `REZ_BINARY_ARCHIVE_PAYLOAD_PREFIX` (`:19-22`) |
| `pypi` | `systems/pypi.rs` | `python -m pip --version` (`:33-39`) / no-op / no-op / no-op / `python -m pip install --disable-pip-version-check --target <install>/python [--no-deps] [-r <req>] <spec>` (`:102-134`). Falls back to `"<name>==<version>"` when no env spec is given (`:138-144`) | `build_system` ∈ {`pypi`, `pip`, `rez_pip`}; env vars `REZ_PYPI_PACKAGE`, `REZ_PYPI_REQUIREMENT`, `REZ_PYPI_EXTRA_ARGS`, `REZ_PYPI_WITH_DEPS` (`:14-17`) |
| `custom` | `systems/custom.rs` | no-op (`:68-80`) / for a real script name, run `<script> build` (`:82-104`, `:276-321`) / no-op (`:106-119`) / no-op (`:121-133`) / `default`\|`copy-only` → copy source tree; `build_command` → run the command then copy the source tree; anything else → run `<script> install` (`:135-148`, `:276-321`) | `build_command` (checked **first**, `mod.rs:158-168`), else `build_system` used as a *script filename* for unrecognised values (`mod.rs:184-188`), else `rezbuild.py` (`mod.rs:192-196`), else file sniffing (`mod.rs:118-153`) |

Selection precedence in `BuildSystem::detect_with_package` (`systems/mod.rs:156-199`):
1. `package.build_command` — `"false"` or `""` → `Custom("copy-only")`, anything else → `Custom("build_command")`;
2. `package.build_system` — one of the 7 named systems, else `Custom(<verbatim string>)`;
3. `rezbuild.py` exists → `Custom("rezbuild.py")`;
4. `build.sh`/`build.bat`/`build.py`/`build` → `Custom(<name>)`; then `CMakeLists.txt`, `Makefile`, `setup.py`/`pyproject.toml`, `package.json`, `Cargo.toml`; else `Custom("default")`.

### rez spec side

Upstream ships **three** build_system plugin modules (`<SP>/rezplugins/build_system/`):

- **`cmake.py`** — the only fully-featured plugin. Configures with `cmake`, then runs the generator binary, then runs `make install` as a third shell invocation; injects a 14-file macro library from `cmake_files/` via `CMAKE_MODULE_PATH`.
- **`custom.py`** — runs the package's `build_command`.
- **`make.py`** — a **non-functional stub**:

```python
# <SP>/rezplugins/build_system/make.py:21-24
    def __init__(self, working_dir, opts=None, package=None, write_build_scripts: bool = False,
                 verbose: bool = False, build_args=[], child_build_args=[]) -> None:
        super(MakeBuildSystem, self).__init__(working_dir)
        raise NotImplementedError
```

`make` survives only because `cmake` declares it as its child (`<SP>/rezplugins/build_system/cmake.py:71-73`, `child_build_system() -> "make"`) so auto-detection de-duplicates. Real Makefile projects go through `custom` + `build_command`, e.g. upstream's own test fixture:

```python
# <SP>/rez/data/tests/builds/packages/hello/1.0/package.py:9
build_command = "make -f {root}/Makefile {install}"
```

**`scons`, `python`, and `bez` do not exist upstream** — verified absent in 3.4.0, on `main`, and at tags `2.72.0` / `2.100.0`. (`when they were removed` → UNVERIFIED, no history bisect performed.)

`rezconfig.py` in that directory is a config-defaults module, explicitly skipped during discovery (`<SP>/rez/plugin_managers.py:165`).

### Comparison

| Upstream plugin | rez-next equivalent | Notes |
|---|---|---|
| `cmake` | `cmake` | Both present. rez-next's is much thinner (no `cmake_files/` macro library, no generator selection, no `--build-target`). |
| `custom` | `custom` + `build_command` handling | Present, but timing differs (see §3). |
| `make` | `make` | Upstream's is a stub; rez-next's actually runs `make`. **rez-next is ahead here in raw capability, but behind in fidelity**: upstream's `make` exists only for de-duplication. |
| — | `python` | rez-next extension (no upstream `python` plugin) |
| — | `nodejs` | rez-next extension |
| — | `cargo` | rez-next extension |
| — | `binary_archive` | rez-next extension — this is the one VX relies on most directly |
| — | `pypi` | rez-next extension (aliases `pip`, `rez_pip`) |

**判定: INTENTIONAL DEVIATION** (rez-next deliberately ships a superset of native implementations instead of upstream's three Python plugins), with two real sub-gaps: (a) no `cmake_files/` macro library, so upstream packages that `#include <RezBuild.cmake>` cannot build; (b) `make` is wired as a first-class system rather than a de-duplication child of `cmake`, so a directory containing both `CMakeLists.txt` and `Makefile` resolves to `cmake` in rez-next only because `cmake` is checked first (`systems/mod.rs:129`) — there is no `child_build_system()` concept at all.

**VX impact: NON-BLOCKING.** VX's prebuilt-binary packages use a `build.py` script (`custom`), not cmake or make, so neither sub-gap is on the critical path. `binary_archive` being a first-class native system is a net win for VX.

---

## 2. Custom build_system plugin registration protocol

### rez-next: two entirely separate mechanisms

**(a) Rust — no user extensibility.** The build system set is a closed enum. `create_build_system()` (`crates/rez-next-build/src/lib.rs:88-104`) maps a name to a hardcoded variant:

```rust
// crates/rez-next-build/src/lib.rs:99-102
"custom" => Some(BuildSystem::Custom(systems::CustomBuildSystem::new("default".to_string()))),
_ => None,
```

There is no registry, no dynamic loading, no entry points. A user cannot register a new Rust build system.

**(b) Python — a faithful port of upstream's protocol, with zero plugins loaded.** `rez-next/crates/rez-next-python/python/rez_next/plugin_managers.py` is close to a line-for-line port of `<SP>/rez/plugin_managers.py`:

- plugin type registered as `type_name = "build_system"` (`plugin_managers.py:291-294`), registered into the singleton at `:322`;
- discovery via namespace walk then entry points (`:103-107`):

```python
# crates/rez-next-python/python/rez_next/plugin_managers.py:109-114
    def _load_from_namespace(self) -> None:
        """Load plugins from ``rezplugins.<type_name>`` namespace."""
        type_module_name = f"rezplugins.{self.type_name}"
        try:
            package = importlib.import_module(type_module_name)
        except ImportError:
            return
```

```python
# crates/rez-next-python/python/rez_next/plugin_managers.py:137-141
    def _load_from_entry_points(self) -> None:
        """Load plugins registered as ``rez.plugins.<type_name>`` entry points."""
        group = f"rez.plugins.{self.type_name}"
```

- module contract: the module must expose a module-level `register_plugin()` returning the class (`:157-170`).

The base class `BuildSystem` (`rez-next/crates/rez-next-python/python/rez_next/build_system.py:153`) requires `name()`, `is_valid_root()`, `build()` and offers `child_build_system()` (`:176-183`), `bind_cli()` (`:186-195`), `set_standard_vars()` (`:249-303`), `add_pre_build_commands()` (`:304-336`), `add_standard_build_actions()` (`:337-368`).

**However: no plugin modules ship.** Evidence:

```console
$ find rez-next -type d -name rezplugins   # (excluding target/)
<no results>
$ grep -rn "def register_plugin" --include=*.py rez-next
crates/.../plugin_managers.py:93:    def register_plugin(          # method, not a module-level factory
crates/.../plugin_managers.py:218:    def register_plugin_type(     # method
```

With no `rezplugins` package importable, `_load_from_namespace` returns at the `ImportError`, and `_load_from_entry_points` finds nothing unless a third-party distribution declares `rez.plugins.build_system`. Therefore `get_buildsys_types()` (`build_system.py:49-56`, delegating to `plugin_manager.get_plugins("build_system")`) returns `[]` on a stock install, and `create_build_system()` (`build_system.py:106-147`) always raises `BuildSystemError`.

Nothing in production code calls it: a repo-wide grep for `add_standard_build_actions`, `get_valid_build_systems`, and `create_build_system(` finds only unit tests (`rez-next/tests/test_build_system.py`, `crates/rez-next-python/tests/test_build_module.py:93`) and the unrelated Rust factory. `rez_next.exceptions.BuildSystemError` does exist (`crates/rez-next-python/src/exceptions_bindings.rs:48`).

### rez spec side

- Base class: `<SP>/rez/build_system.py:126` — **in `rez/`, not `rezplugins/build_system/build_system.py`** (that file does not exist).
- Discovery: `<SP>/rez/plugin_managers.py:132-134` (`load_plugins_from_namespace` + `load_plugins_from_entry_points`), namespace entry point `<SP>/rezplugins/build_system/__init__.py:5-6` (`extend_path`), entry-point group `rez.plugins.build_system` (`plugin_managers.py:194`).
- Module contract: `<SP>/rez/plugin_managers.py:244-247` — `plugin_module.register_plugin()` returning the class. Confirmed at the bottom of each plugin (`cmake.py:314`, `custom.py:291`, `make.py:27`).
- Required method:

```python
# <SP>/rez/build_system.py:205-211
    def build(self,
              context: ResolvedContext,
              variant: Variant,
              build_path: str,
              install_path: str,
              install: bool = False,
              build_type=BuildType.local) -> BuildResult:
```

- Return type `BuildResult` TypedDict `{success, extra_files, build_env_script}` (`<SP>/rez/build_system.py:25-28`).
- Exception `rez.exceptions.BuildSystemError(BuildError)` (`<SP>/rez/exceptions.py:147-149`).
- Selection from `package.py`: `<SP>/rez/build_system.py:61-70` — `build_command` wins over `build_system`; both are consumed as plugin *names*.

rez-next's Python signature is character-identical (`build_system.py:223-231`), including the default `build_type: BuildType = None` oddity.

**判定: GAP (needs rez-next work).** The protocol is faithfully ported but is dead code: zero plugin modules ship, so the entire Python build-system API raises or returns empty. The Rust side is a closed enum with no registration hook, so there is no supported way for a third party to add a build system at all.

**VX impact: NON-BLOCKING** for the pilot (VX uses the `custom` script path, which works), but it means the documented `rez.plugins.build_system` extension route is unavailable — VX cannot ship a build system as a plugin and must keep relying on in-package `build.py` scripts.

---

## 3. `build_command` / `pre_build_commands` / `post_build_commands`

### `build_command`

**Honoured: yes**, with caveats. It is consumed in two places:

- Selection: `systems/mod.rs:158-168` — `build_command` is checked **before** `build_system`, so setting it silently overrides `build_system`. `"false"`/`""` → copy-only.
- Execution: `systems/custom.rs:188-242` (`execute_build_command`), reached from the **Installing** step (`custom.rs:142`). Variables expanded at `custom.rs:245-273`:

```rust
// crates/rez-next-build/src/systems/custom.rs:253-271
expanded = expanded.replace("{root}", &request.source_dir.to_string_lossy());
expanded = expanded.replace("{install}", "install");
expanded = expanded.replace("{build_path}", &environment.get_build_dir().to_string_lossy());
expanded = expanded.replace("{install_path}", &environment.get_install_dir().to_string_lossy());
expanded = expanded.replace("{name}", &request.package.name);
...
expanded = expanded.replace("{variant_index}", "");
```

- On success, rez-next additionally copies the whole source tree into the install dir (`custom.rs:213`).
- rez-next's `Package.build_command` is `Option<String>` (`crates/rez-next-package/src/package/types.rs:32`); the AST parser accepts only a string/number/bool literal (`python_ast_parser/mod.rs:219-221` → `extract.rs:11-33`, which errors on anything else). `build_command = False` survives as the string `"false"` (`extract.rs:16`).

### `pre_build_commands`

**Honoured in the Rust build path: no.** The field exists and round-trips (`package/types.rs:42` → `python_ast_parser/mod.rs:263-264` → `package/serialize.rs:33,410,553,597`), but a grep across `crates/rez-next-build/src/` for `pre_build_commands` returns **zero** hits. It is never executed during a build.

It is implemented only in the Python skeleton (`crates/rez-next-python/python/rez_next/build_system.py:304-336`), which nothing calls in production (see §2).

### `post_build_commands`

**Does not exist.** It is absent from the `Package` struct (`package/types.rs:8-89`) and from the AST parser (`python_ast_parser/mod.rs` has no `"post_build_commands"` arm). It appears in exactly one place — the serialiser's key-ordering constant:

```rust
// crates/rez-next-serialise/src/package_serialise.rs:71-73
    "pre_build_commands",
    "build_commands",
    "post_build_commands",
```

which is inert ordering metadata only.

### rez spec side

- `build_command` — `<SP>/rez/package_maker.py:88`: `Optional("build_command"): Or([str], str, False)`. A **list of strings is legal upstream**; rez-next rejects it.
- Expansion set (`<SP>/rezplugins/build_system/custom.py:44-54`): `root`, `install`, `build_path`, `install_path`, `name`, `variant_index`, `version` — identical names to rez-next. Two differences: upstream's `{install}` expands to `"install"` **or `""`** depending on whether an install is occurring (`custom.py:157`), whereas rez-next always emits `"install"` (`custom.rs:254`); upstream's `{variant_index}` expands to the real index or `""` (`custom.py:158`), whereas rez-next always emits `""` (`custom.rs:271`).
- `pre_build_commands` — `<SP>/rez/package_maker.py:83`, schema `_commands_schema` (`<SP>/rez/package_resources.py:206-211`) = `Or(SourceCode, callable, str, [str])`. Implemented at `<SP>/rez/build_system.py:305-340`. Inside the body, `this` (a `VariantBinding`) and `build` (`{build_type, install, build_path, install_path}`) are bound.
- `post_build_commands` — **does not exist upstream either.** Exhaustive grep over `rez/` and `rezplugins/` returns no matches. Do not confuse it with `post_commands` (runtime, `package_maker.py:82`) or `post_release_commands` (a release-hook plugin setting, `<SP>/rezplugins/release_hook/rezconfig.py:105`).

**Upstream timing, precisely.** Both live build systems pass `add_pre_build_commands` as `post_actions_callback` (`cmake.py:168-175`, `custom.py:179-186`). Ordering inside the generated build script (`<SP>/rez/resolved_context.py:1509-1541`):

1. `actions_callback` → `_add_build_actions` → all `REZ_BUILD_*` variables set;
2. `_execute(executor)` → the resolved requires' own `commands()` interpreted;
3. `post_actions_callback` → **`pre_build_commands` runs here** — inside the fully-resolved build environment, after the requires' commands, before the build command;
4. shell spawned → **build command runs**.

There is no separate install step upstream: `build()` is called once with `install: bool`. For `cmake` there is a third shell pass running `make install` (`cmake.py:238-249`) which re-runs the callbacks, so `pre_build_commands` executes **again** before the install sub-shell. **Nothing runs after install.**

**判定: GAP (needs rez-next work).**
- `build_command` is honoured but (i) runs in the **Installing** step rather than the build step, (ii) always expands `{install}` to `"install"` and `{variant_index}` to `""`, (iii) is followed by an unconditional copy of the source tree into the payload, and (iv) does not accept the list form.
- `pre_build_commands` is parsed but never executed by the build path — silent no-op.
- `post_build_commands` is listed in a serialiser constant but is not a real field on either side. That constant is misleading and should be trimmed (it is not an upstream key).

**VX impact: NON-BLOCKING** for prebuilt-binary packages (they do not use `pre_build_commands`), but the unconditional source-tree copy after `build_command` is a **payload-pollution hazard**: with `build_command` set, `package.py` and every other source file land in `<install>/` alongside the payload, which will break VX's byte-comparison acceptance criterion ("新路径与原 `build_bundle.py` 产出的仓库内容可比对") and its "zero symlink / `payload` naming" invariants if any source file is added later.

---

## 4. Build-time environment variables

All of them are set in one place: `BuildEnvironment::with_install_path` (`crates/rez-next-build/src/environment.rs:45-142`), with per-variant updates at `:215-250` and source-path updates at `:253-264`.

| Variable | Present? | Evidence |
|---|---|---|
| `REZ_BUILD_ENV` | yes | `environment.rs:70` — always `"1"` |
| `REZ_BUILD_TYPE` | **yes, but hardcoded** | `environment.rs:72-74` — `env_vars.insert("REZ_BUILD_TYPE".to_string(), "local".to_string());` with the comment *"Default to `local` for now; can be configured via BuildConfig later"*. `BuildType::Central` exists (`lib.rs:33-38`) but is never wired into the environment, so `central` is unreachable. |
| `REZ_BUILD_INSTALL` | yes | `environment.rs:78-79` — `"1"` iff an install path was supplied |
| `REZ_BUILD_INSTALL_PATH` | yes | `environment.rs:95-98`; re-set after the variant subpath is applied (`:245-248`) |
| `REZ_BUILD_PATH` | yes | `environment.rs:99-102`; re-set after the variant subpath is applied (`:241-244`) |
| `REZ_BUILD_SOURCE_PATH` | yes | `environment.rs:253-257` (`set_source_path`, called from `builder.rs:313`) and `:282-287` |
| `REZ_BUILD_PROJECT_FILE` | yes | `environment.rs:258-263` and `:278-281` |
| `REZ_BUILD_PROJECT_NAME` | yes | `environment.rs:88` |
| `REZ_BUILD_PROJECT_VERSION` | yes | `environment.rs:89-93` (defaults to `"0.0.0"` when unversioned, `:11`, `:82-86`) |
| `REZ_BUILD_PROJECT_DESCRIPTION` | yes | `environment.rs:103-111` (trimmed; `""` when absent) |
| `REZ_BUILD_VARIANT_INDEX` | yes | default `"0"` at `environment.rs:119`; real value via `set_variant_env` at `:215-219` (called from `builder.rs:318-321`) |
| `REZ_BUILD_VARIANT_REQUIRES` | yes | default `""` at `environment.rs:120`; real value (space-joined) at `:220-223` |
| `REZ_BUILD_VARIANT_SUBPATH` | yes | default `""` at `environment.rs:121`; real value at `:228-233` and `:249` |
| `REZ_BUILD_THREAD_COUNT` | yes | `environment.rs:112-115`, from `rez_next_common::utils::get_thread_count(None)` — **not** from a `build_thread_count` config setting |
| `REZ_BUILD_REQUIRES` | yes | `environment.rs:328` (requires + build_requires + private_build_requires + variant requires, space-joined) |
| `REZ_BUILD_REQUIRES_UNVERSIONED` | yes | `environment.rs:329-332` |
| `REZ_BUILD_PACKAGE_NAME` | yes — **non-upstream** | `environment.rs:87` |
| `REZ_BUILD_PACKAGE_VERSION` | yes — **non-upstream** | `environment.rs:89-92` |
| `REZ_BUILD_TARGET_PLATFORM` | **absent** | no Rust code sets it; only propagated from the caller's own environment by `collect_build_plugin_env_vars` (`src/cli/commands/build.rs:556-563`, which whitelists `REZ_BUILD_TARGET_*`, `REZ_BINARY_ARCHIVE_*`, `REZ_PYPI_*`) |
| `REZ_BUILD_TARGET_ARCH` | **absent** | same |
| `REZ_BUILD_TARGET_OS` | **absent** | same |

The canonical set is asserted by a test that lists 16 names and fails if any is missing (`crates/rez-next-build/src/tests.rs:763-816`, list at `:775-792`), and variant values are asserted at `:591-642`.

### rez spec side

Single implementation site: `<SP>/rez/build_system.py:241-303`, `BuildSystem.set_standard_vars()`. The set is **exactly** the 16 above minus the two `PACKAGE_*` extras:

| Variable | file:line |
|---|---|
| `REZ_BUILD_ENV` | `rez/build_system.py:264` |
| `REZ_BUILD_PATH` | `:265` |
| `REZ_BUILD_THREAD_COUNT` | `:266` — `literal(str(package.config.build_thread_count))`, config default `"physical_cores"` (`rez/rezconfig.py:791`) |
| `REZ_BUILD_VARIANT_INDEX` | `:267` |
| `REZ_BUILD_VARIANT_REQUIRES` | `:268` |
| `REZ_BUILD_VARIANT_SUBPATH` | `:269` |
| `REZ_BUILD_PROJECT_VERSION` | `:270` |
| `REZ_BUILD_PROJECT_NAME` | `:271` |
| `REZ_BUILD_PROJECT_DESCRIPTION` | `:272` |
| `REZ_BUILD_PROJECT_FILE` | `:273` |
| `REZ_BUILD_SOURCE_PATH` | `:274-278` |
| `REZ_BUILD_REQUIRES` | `:279-283` |
| `REZ_BUILD_REQUIRES_UNVERSIONED` | `:284-288` |
| `REZ_BUILD_TYPE` | `:289` — `build_type.name`, i.e. `"local"` or `"central"` |
| `REZ_BUILD_INSTALL` | `:290` |
| `REZ_BUILD_INSTALL_PATH` | `:293-294` — **only when `install_path` is truthy** |

Plus a conditional `REZ_IN_REZ_RELEASE` (`:296-299`). All values are wrapped in `rez.rex.literal` with an explicit shell-injection warning at `:257-262`.

**`REZ_BUILD_PACKAGE_NAME` / `REZ_BUILD_PACKAGE_VERSION` do not exist upstream** — upstream uses only the `PROJECT_` spelling. `REZ_BUILD_TARGET_PLATFORM` / `_ARCH` / `_OS` are **rez-next inventions**: they are read by `rez-next/crates/rez-next-build/assets/build_plugins.py:47-49` but nothing sets them, so they silently fall back to host values.

**判定:**
- The 16 canonical variables: **ALIGNED**.
- `REZ_BUILD_PACKAGE_NAME` / `REZ_BUILD_PACKAGE_VERSION`: **INTENTIONAL DEVIATION** (harmless superset, but `build_plugins.py` reads the non-upstream spelling at `:57-58`, so scripts written against rez-next will not run on upstream Rez).
- `REZ_BUILD_TYPE` hardcoded to `"local"`: **GAP (needs rez-next work)** — `REZ_BUILD_TYPE=central` is unreachable even though `BuildType::Central` and `get_build_process_types() == ["local","central"]` exist.
- `REZ_BUILD_TARGET_PLATFORM` / `_ARCH` / `_OS`: **GAP (needs rez-next work)** — declared-by-consumption in `build_plugins.py` but never emitted; silent host fallback is worse than an error.
- `REZ_BUILD_THREAD_COUNT` is not config-driven: **GAP (minor)** — upstream honours `config.build_thread_count` per package.

**VX impact: NON-BLOCKING for the pilot, BLOCKING for correctness of cross-builds.** VX's `build.py` must target `platform-<p>/arch-<a>` from `REZ_BUILD_VARIANT_REQUIRES` / `REZ_BUILD_VARIANT_SUBPATH` (both set correctly) rather than from `REZ_BUILD_TARGET_*` (never set). Any VX script that reads `REZ_BUILD_TARGET_ARCH` will silently build the wrong payload on a cross-target CI runner.

---

## 5. `variants` / `variant_requires`

### rez-next

- `Package.variants: Vec<Vec<String>>` (`crates/rez-next-package/src/package/types.rs:24`); parsed by `extract_variants` (`python_ast_parser/mod.rs:243-245`).
- **Built one at a time, sequentially.** `BuildManager::start_build` refuses to start when a package has variants and no explicit index was chosen:

```rust
// crates/rez-next-build/src/builder.rs:274-279
        if !request.package.variants.is_empty() && request.variant_index.is_none() {
            return Err(RezCoreError::BuildError(format!(
                "Package '{}' requires an explicit variant selection",
                request.package.name
            )));
        }
```

and `start_build` returns exactly one build id (`:281-282`). The CLI fans out: `src/cli/commands/build.rs:215-220` builds all variant indices when none are given, and `:227-253` loops, resolving a **fresh context per variant** (`:234`) and running a full build+install per iteration. It also validates that the request's `variant_requires` match `package.variants[index]` (`builder.rs:288-295`).
- Subpath naming: `PackageInstallLayout::for_variant` (`crates/rez-next-package/src/install_layout.rs:33-94`). Non-hashed variants push each *canonical* requirement as one path component (`:82-86`); hashed variants use SHA-1 of a Python-list representation (`:64-80`):

```rust
// crates/rez-next-package/src/install_layout.rs:67-80
                let python_list = format!("[{}]", canonical.iter().map(|value| format!("'{value}'")).collect::<Vec<_>>().join(", "));
                let digest = Sha1::digest(python_list.as_bytes());
```

  Verified: `sha1("['platform-linux', 'arch-x86_64'])")` = `4cd91c759bd6e4d7ef09736380d9e5b18c81a0f2`, matching the committed expectation at `crates/rez-next-package/tests/install_layout_contract.rs:52`.
- The subpath is joined onto both build and install dirs, and `REZ_BUILD_PATH` / `REZ_BUILD_INSTALL_PATH` / `REZ_BUILD_VARIANT_SUBPATH` are re-pointed accordingly (`environment.rs:236-250`).
- `hashed_variants` is supported (`types.rs:80`, `install_layout.rs:64`).
- Requirements that are not in a supported canonical form are rejected rather than silently mangled (`install_layout.rs:163-227`), including namespaces, platform/env conditions, and non-ASCII.

### rez spec side

- `variants` authored as a list of lists (`<SP>/rez/package_maker.py:65-66`), "deliberately not possible to late bind".
- `variant_requires` is **not** an authorable package attribute — it is the runtime property `Variant.variant_requires`, consumed at `<SP>/rez/build_system.py:250` and in `_subpath`.
- One build+install per variant: `LocalBuildProcess` fans out via `visit_variants` (`<SP>/rezplugins/build_process/local.py:68-73`), resolving a fresh context per variant (`<SP>/rez/build_process.py:256-299`) before `build_system.build(...)` (`local.py:268-274`).
- Subpath (`<SP>/rez/package_resources.py:493-521`):

```python
        if self.parent.hashed_variants:
            vars_str = str(list(map(str, self.variant_requires)))
            h = sha1(vars_str.encode("utf8"))
            hashdir = h.hexdigest()
            ...
            return hashdir
        else:
            dirs = [x.safe_str() for x in self.variant_requires]
            subpath = os.path.join(*dirs)
            return subpath
```

- `use_variant_shortlinks` (symlinks under `_v/`, `package_resources.py:502-515`) is a second opt-out that rez-next does not implement. rez-next *declares* the config keys —

```python
# rez-next/crates/rez-next-python/python/rez_next/config.py:747,750
variant_shortlinks_dirname: str = "_v"
use_variant_shortlinks: bool = True
```

  — but no Rust code reads them (`grep -rn "use_variant_shortlinks\|variant_shortlinks_dirname" --include=*.rs crates/ src/` → no results), and `install_layout.rs:17` explicitly documents that "Optional repository shortlinks are not canonical installation paths."

**判定: ALIGNED.** Same one-variant-at-a-time model, same fresh-context-per-variant, same `platform-linux/arch-x86_64` subpath convention, and the hashed-variant SHA-1 formula is byte-identical (verified by computing it, above). Three minor divergences: rez-next does not implement `use_variant_shortlinks` (though it advertises the config keys), rez-next *requires* an explicit variant index where upstream defaults to building all, and rez-next rejects non-canonical requirement syntax that upstream would normalise via `safe_str()`.

**VX impact: NON-BLOCKING, in fact the strongest area of alignment.** The `<prefix>/<name>/<version>/platform-<p>/arch-<a>/payload/...` layout VX needs is produced exactly by this code path.

---

## 6. `requires` / `build_requires` / `private_build_requires`

### rez-next

All three are fields on `Package` (`crates/rez-next-package/src/package/types.rs:18-22`) and are parsed (`python_ast_parser/mod.rs:231-239`). They are consumed in two places:

1. Build-context resolution — concatenated and de-duplicated into the resolve request:

```rust
// src/cli/commands/build.rs:465-471
    for requirement in package
        .requires
        .iter()
        .chain(package.build_requires.iter())
        .chain(package.private_build_requires.iter())
        .chain(variant_requires.unwrap_or(&[]).iter())
```

2. `REZ_BUILD_REQUIRES` / `REZ_BUILD_REQUIRES_UNVERSIONED` (`environment.rs:310-332`).

No distinction is made anywhere between `build_requires` and `private_build_requires` — upstream's transitivity rule is not modelled. Both are simply appended.

Neither is stripped from the installed package: the plain build path writes no package definition at all (see §10/G5 below), and the only path that does copy `package.py` copies it verbatim (`release.rs:589-597`). So `build_requires` leak into the installed package's runtime requires.

### rez spec side

Schema (`<SP>/rez/package_maker.py:61-63`) — all three `late_bound([package_request_schema])`. Semantics, from the official docs `<SP>/rez/../../docs/source/building_packages.rst:32-42` (verbatim):

> * First, the package's `requires` list is used;
> * Then, the package's `build_requires` is appended. This is transitive, meaning that the `build_requires` of all other packages in the environment are also used;
> * Then, the package's `private_build_requires` is appended (unlike `build_requires`, it is not transitive).
> * Finally, if the package has variants, the current variant's requirements are appended.

Consumed at `<SP>/rez/packages.py:433-451` via `get_requires(build_requires=…, private_build_requires=…)`; the only production caller passing both `True` is the build-context constructor (`<SP>/rez/build_process.py:259-260`).

On persistence: both attributes are **not** in `package_build_only_keys` (`<SP>/rez/package_resources.py:42-48`), so they do persist into the installed package definition — but the installed variant's effective runtime `requires` is unaffected, because resolution never calls `get_requires(build_requires=True, …)` outside the build path.

**判定: PARTIAL — GAP (needs rez-next work).** The three-way distinction is parsed but not honoured: (a) no transitivity difference between `build_requires` and `private_build_requires`; (b) nothing strips them from the installed definition, and because rez-next's `Package.requires`/`build_requires` are separate fields that downstream resolution treats symmetrically, `build_requires` risk becoming runtime requirements.

**VX impact: NON-BLOCKING** — VX's prebuilt-binary packages declare no `build_requires` (see `rez-next/tests/fixtures/vx_rez_package/package.py`, which does, but that is a test fixture). It becomes relevant the moment a VX package needs a build-time-only tool.

---

## 7. `rez build` CLI arguments

`BuildArgs` is defined at `rez-next/src/cli/commands/build.rs:40-126`. Wired into the CLI at `src/cli/mod.rs:66-67` (`Build(commands::build::BuildArgs)`) and dispatched at `:243`.

| Flag | Exists? | Used? | Notes |
|---|---|---|---|
| `--install`, `-i` | yes | yes | `build.rs:45-47`; drives `get_install_path` at `:178-182` |
| `--release`, `-r` | yes | yes | `build.rs:85-87`; selects `config.release_packages_path` vs `local_packages_path` at `:1281-1285`. **Note: this is a rez-next extension — upstream has no `--release` on `rez-build`** |
| `--prefix`, `-p` | yes | yes | `build.rs:49-51`; `:1277-1279` |
| `--variants` | yes | yes | `build.rs:73-75` (`Option<Vec<usize>>`, zero-indexed); range-validated with a warning at `:185-220`. Upstream additionally supports negative (from-the-end) indices |
| `--clean`, `-c` | yes | **cosmetic only** | `build.rs:41-43`; the only use is `force_rebuild: args.force \|\| args.clean` at `:170`. `BuildOptions::force_rebuild` (`builder.rs:181`) is **never read** anywhere in the crate — verified by grep: it appears only at `builder.rs:181`, `build.rs:170`, `release.rs:124`, `build_functions.rs:51`, and in tests. `BuildConfig::clean_before_build` (`builder.rs:36,68`) is likewise never read. **No directory is ever cleaned.** |
| `--force`, `-f` | yes | **cosmetic only** (same dead `force_rebuild`) | `build.rs:94-96` |
| `--paths` | **no** | — | `--paths` exists on `rez env`, `rez depends`, `rez test` (e.g. `tests/cli_e2e_tests.rs:92`), not on `rez build`. Upstream also has no `--paths` on `rez-build` |
| `--keep-tmp` | **no** | — | The nearest control is `BuildConfig::keep_artifacts` (`builder.rs:38`, default `true`, `:69`), read once at `process.rs:635` to decide whether the temp dir is removed in the Cleanup step. No CLI flag exposes it. Upstream has no `--keep-tmp` either (only `--keep-tmpdirs` on `rez-selftest`) |
| `--process` | declared, **ignored** | no | `build.rs:65-67` with `default_value = "local"`. A count of `args.process` in `build.rs` returns **0** |
| `--build-system`, `-b` | declared, **ignored** | no | `build.rs:69-71`. Count of `args.build_system` in `build.rs` = **0**. Build-system choice therefore comes only from `package.py` |
| `--build-args`, `--ba` | yes | yes | `build.rs:77-79` → `parse_build_args` (`:549-554`) → `BuildOptions.build_args`. Consumed **only** by the cmake system (`cmake.rs:41`) |
| `--child-build-args`, `--cba` | declared, **ignored** | no | `build.rs:81-83`. Count = **0** (upstream's child-build-system concept has no rez-next counterpart) |
| `--fail-graph` | declared, **ignored** | no | `build.rs:53-55`. Count = **0** |
| `--scripts`, `-s` | declared, **ignored** | no | `build.rs:57-59`. Count = **0** |
| `--view-pre` | yes | yes | `build.rs:61-63`, handled at `:161-163` (prints a hand-written Python rendering, `:566-597`) |
| `--skip-tests` | yes | yes | `build.rs:89-91` → `BuildOptions.skip_tests`, read at `process.rs:413` and `:426` |
| `--verbose`, `-v` | yes | yes | `build.rs:97-99` (7 uses) |
| `--output` | yes | yes | `build.rs:101-103` (`auto`\|`compact`\|`full`) |
| `--tui` | yes | yes | `build.rs:105-107` (ratatui live dashboard, `:711-748`) |
| `--source`, `--subdir`, `--reference` | yes | yes | `build.rs:116-125` — rez-next extension: build straight from a Git/HTTP/SSH source |

Usage counts above were produced with:

```console
$ for f in clean install prefix fail_graph scripts view_pre process build_system variants \
           build_args child_build_args release skip_tests force verbose output tui source subdir reference; do
    printf 'args.%s -> %s\n' "$f" "$(grep -c "args\.$f" src/cli/commands/build.rs)"; done
args.clean -> 1        args.install -> 1     args.prefix -> 1      args.fail_graph -> 0
args.scripts -> 0      args.view_pre -> 1    args.process -> 0     args.build_system -> 0
args.variants -> 1     args.build_args -> 1  args.child_build_args -> 0
args.release -> 2      args.skip_tests -> 1  args.force -> 1       args.verbose -> 7
args.output -> 3       args.tui -> 1         args.source -> 1      args.subdir -> 1
args.reference -> 1
```

### rez spec side

`<SP>/rez/cli/build.py`, split into `setup_parser` (build-only, `:87-107`) and `setup_parser_common` (shared with `rez-release`, `:35-84`):

| Flag | Default | file:line |
|---|---|---|
| `-c`, `--clean` | `store_true` | `rez/cli/build.py:88-90` |
| `-i`, `--install` | `store_true` | `:91-94` |
| `-p`, `--prefix` | `metavar='PATH'` | `:95-97` |
| `--fail-graph` | `store_true` | `:98-101` |
| `-s`, `--scripts` | `store_true` | `:102-105` |
| `--view-pre` | `store_true` | `:106-108` |
| `--process` | `choices=process_types`, default `config.default_build_process` = `"local"` | `:43-47` |
| `-b`, `--build-system` | `choices=types` | `:64-69` |
| `--variants` | `nargs='+', type=int` | `:70-73` |
| `--ba`, `--build-args` | | `:74-77` |
| `--cba`, `--child-build-args` | | `:78-81` |

Upstream has **no** `--no-install`, `--release`, `--paths`, `--keep-tmp`, `-j`, `--stats`, `--job-template`, `--dry-run`, `--extra-packages`, or `--source-variant` on `rez-build`. Note `-c` is `--clean` and `-b` is `--build-system` upstream — rez-next matches this. Argument-after-`--` groups are enabled via `"build": {"arg_mode": "grouped"}` (`<SP>/rez/cli/_util.py:26-33`).

**判定:**
- Flag *surface*: **ALIGNED / superset**. rez-next has every upstream flag plus `--release`, `--source/--subdir/--reference`, `--skip-tests`, `--tui`, `--output`, `--force`.
- **GAP (needs rez-next work):** five declared flags are silently accepted and ignored (`--process`, `-b/--build-system`, `--cba`, `--fail-graph`, `-s/--scripts`), and `--clean`/`--force` are no-ops because `force_rebuild` and `clean_before_build` are write-only. Silently ignoring `-b/--build-system` is the most dangerous: a caller who passes it believes they overrode the package's build system when they did not.
- `--paths` and `--keep-tmp`: **ALIGNED by absence** — neither exists upstream on `rez-build` either. Note `sub1-wrapper.md` already records that "`rez build` 没有 `--repository` 参数".

**VX impact: BLOCKING for the `vx build` wrapper as specified.** The wrapper's planned invocation is `rez build <source> --install --prefix <repo> --build-system build.py`; `--build-system` is a no-op, so the selection must come from `package.py`'s `build_system = "build.py"` (which does work — but `sub1`'s acceptance criterion "`build_system = "custom"` 必须被测试拒绝" needs to be re-scoped: `custom` is *not* rejected today, it silently degrades to `Custom("default")` copy-only, upstream gap G8). Additionally `--clean` cannot be relied on to clear a stale build directory.

---

## 8. Build process model (`BuildProcess` / `BuildStep`)

### rez-next

`BuildProcess` (`crates/rez-next-build/src/process.rs:16-35`) holds build id, request, environment, config, status, output/errors, start time and a child-process handle. `BuildStep` is an 8-variant enum:

```rust
// crates/rez-next-build/src/process.rs:39-56
pub enum BuildStep {
    Preparing, Configuring, Compiling, Testing, Packaging, Installing, PackageTesting, Cleanup,
}
```

The fixed ordered sequence is at `process.rs:288-297`, dispatched at `:402-433`:

| Step | Handler | What it does |
|---|---|---|
| `Preparing` | `process.rs:447-471` | `mkdir -p` build dir and install dir |
| `Configuring` | `:474-488` | `BuildSystem::detect_with_package(...).configure(...)` |
| `Compiling` | `:491-507` | `.compile(...)` |
| `Testing` | `:510-522` | `.test(...)`, or short-circuits to success when `options.skip_tests` (`:413-417`) |
| `Packaging` | `:525-538` | `.package(...)` |
| `Installing` | `:541-554` | `.install(...)` |
| `PackageTesting` | `:556-626` | runs `package.tests` against the installed payload, with `pre_test_commands` folded into `post_commands` (`:572-577`) and `{root}`/`{base}`/`{this.root}`/`{this.base}` expansion (`:605-608`) |
| `Cleanup` | `:629-645` | removes the temp dir unless `config.keep_artifacts` |

Failure in any step aborts the sequence (`process.rs:362-376`). Live events (`BuildEvent`, `:77-92`) are emitted for each step start/output/error/finish.

`BuildSystem::detect_with_package` is re-run from scratch in each step handler (`process.rs:480, 497, 516, 530, 546`) rather than being resolved once.

### rez spec side

`BuildProcess` ABC at `<SP>/rez/build_process.py:83`, real logic in `BuildProcessHelper` (`:199`) including `create_build_context(variant, build_type, build_path)` (`:256-299`) and `visit_variants()` (`:210-239`). The concrete implementations are **plugins**, not classes in `build_process.py`:

- `LocalBuildProcess` — `<SP>/rezplugins/build_process/local.py:42`, *"builds a package's variants sequentially and on localhost"*, registered as `"local"`. The only functional implementation.
- Steps: upstream has **no `BuildStep` enum**. The three-phase shape (`configure → build → install`) is internal to each build-system plugin. `cmake.py` performs configure (`execute_shell`), build (`execute_shell`, appending `-j<build_thread_count>` at `:223-226`), and install (`execute_shell`, `:238-249`); `custom.py` performs a single shell invocation whose `{install}` token tells the script whether to install.
- Upstream also has a `PackageTesting`-equivalent run by `LocalBuildProcess`, but there is no `Preparing` or `Cleanup` step object.

**判定: INTENTIONAL DEVIATION.** rez-next replaced upstream's plugin-owned step sequence with a fixed 8-step pipeline. The enumeration is reasonable and covers the same ground (its `Configuring`/`Compiling`/`Installing` map onto cmake's three shells). Two sub-notes: (a) `Packaging` is a no-op in every one of the 8 systems except `cargo` (`cargo package --no-verify`, and even there errors are swallowed), so it is dead weight; (b) `BuildSystem::detect_with_package` being re-invoked per step is redundant work and makes the "which system am I using" decision non-cacheable.

**VX impact: NON-BLOCKING.** For a `build.py` package, the interesting steps are `Compiling` (runs `python build.py build`) and `Installing` (runs `python build.py install`) — see §3 for why that double invocation matters.

---

## 9. Remote build (`--process=remote`)

### rez-next: absent

- `BuildProcess` has exactly one implementation; there is no remote variant.
- `--process` is declared with `default_value = "local"` (`src/cli/commands/build.rs:65-67`) but **never read** (see §7).
- The process-type registry returns the wrong vocabulary entirely:

```rust
// crates/rez-next-build/src/lib.rs:83-85
pub fn get_build_process_types() -> Vec<&'static str> {
    vec!["local", "central"]
}
```

`"local"`/`"central"` are *build types* (`BuildType`, `lib.rs:33-38`, the upstream `REZ_BUILD_TYPE` values), not build *processes*. `BuildType::Central` is never wired into the environment (§4), so `"central"` names something that does not exist either.
- `config.py` mirrors this: `default_build_process: str = "local"` (`crates/rez-next-python/python/rez_next/config.py:753`), and the Python `create_build_process` (`build_process.py:407-445`) looks up `BuildProcess._registry`, which is populated only by `__init_subclass__` (`build_process.py:78-84`) — no concrete subclass exists, so the registry is empty and `create_build_process("local", …)` raises `BuildProcessError`.
- No `REZ_REMOTE_*` config, no job template, no `rezjob`.

### rez spec side

`RemoteBuildProcess` exists but is a stub (`<SP>/rezplugins/build_process/remote.py`, 29 lines total):

```python
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

`--process remote` is accepted (choices come from `plugin_manager.get_plugins('build_process')`, `<SP>/rez/build_process.py:36-39`) and then raises. There are no `REZ_REMOTE_*` config settings; `rezplugins/build_process/rezconfig.py` contains only the SPDX header.

**判定: ALIGNED (both are absent/non-functional), with a rez-next naming bug.** Neither implementation can do a remote build. But rez-next's `get_build_process_types()` returning `["local", "central"]` conflates `BuildType` with build-process, so any caller filtering on "is remote available?" gets a misleading `central` and the genuinely-upstream value `remote` is not recognised at all.

**VX impact: NON-BLOCKING.** VX builds on per-platform CI runners (matrix), so remote build is not needed.

---

## 10. `build_time` / `timestamp` on an installed variant

### rez-next

- `Package.timestamp: Option<i64>` exists as a **field** (`crates/rez-next-package/src/package/types.rs:57-58`) and round-trips through serialisation (`package/serialize.rs`) and the key order (`crates/rez-next-serialise/src/package_serialise.rs:63`). It is settable from `package.py` via `package_maker.py:99-101`.
- **Nothing in the build or release path ever writes it.** A grep for `timestamp\s*=\s*Some` / `\.timestamp =` across the workspace returns only cache, benchmark and test code (`rez-next-package-cache`, `rez-next-cache`, `benches/`) — zero hits in `rez-next-build`. Confirmed: `grep -n "timestamp" crates/rez-next-build/src/release.rs` → no matches.
- `BuildResult` carries `duration_ms` (`builder.rs:206`) but no timestamp. `BuildArtifacts` carries `install_dir`, `files`, `metadata` (`artifacts.rs:11-18`) — no timestamp. `BuildStats` carries aggregate timings only (`builder.rs:79-92`).
- The release path writes a `variant.json` sidecar per variant (`release.rs:558-574`):

```rust
// crates/rez-next-build/src/release.rs:559-563
                let metadata = serde_json::json!({
                    "variant": variant,
                    "index": index,
                    "subpath": layout.variant_subpath(),
                });
```

  — no timestamp, and this file is a rez-next invention with no upstream counterpart (it lands inside the payload directory, so it becomes part of the shipped bytes).
- **No determinism/reproducibility control at all.** No `SOURCE_DATE_EPOCH` handling, no mtime normalisation, no config knob. `copy_file_preserving_permissions` (`binary_archive.rs:357-378`) preserves source permissions; `zip` extraction restores Unix modes on Unix only (`binary_archive.rs:283-292`).

### rez spec side

- `rez-build` records **no** build timestamp: zero `timestamp` hits in `<SP>/rez/build_process.py` and `<SP>/rezplugins/build_process/local.py`.
- `timestamp` is set by the **filesystem package repository at variant-install time**:

```python
# <SP>/rezplugins/package_repository/filesystem.py:1433-1435
        # timestamp defaults to now if not specified
        if not package_data.get("timestamp"):
            package_data["timestamp"] = int(time.time())
```

  Epoch seconds, defaulting to now, preserved only if already present. The surrounding comment (`:1420-1422`) explains the merge rule: when adding a variant to an existing package, existing attributes win so that `timestamp` and release fields are not changed.
- `timestamp` is listed among release-time attributes (`<SP>/rez/package_resources.py:31-39`, `package_release_keys`).
- `rez-cp -k` / `rez-mv -k` preserve it; config `warn_untimestamped` (`<SP>/rez/config.py:480`).
- **No reproducibility control upstream either**: no `SOURCE_DATE_EPOCH` support (the only hit is in vendored `rez/vendor/distlib/scripts.py`), no `build_timestamp`/`deterministic` settings — the only `build_*` config keys are `build_directory`, `build_thread_count`, `default_build_process`.

**判定:**
- "no build time is recorded": **ALIGNED** (neither records one) — but for different reasons: upstream sets `timestamp` in the repository layer, rez-next never sets it anywhere.
- **GAP (needs rez-next work):** rez-next's `Package.timestamp` is a dead input field. Nothing populates it, so `warn_untimestamped`-style tooling, `rez-cp -k`, and the timestamp-based filters that *do* exist in rez-next (`crates/rez-next-package/src/filter.rs:182-236`, `package_order.rs:311-360`) have nothing to work with for anything rez-next itself built.
- **GAP:** the `variant.json` sidecar is an upstream-incompatible extra file written into the payload directory.
- No `SOURCE_DATE_EPOCH`: **ALIGNED (both absent)**, but **VX impact: BLOCKING-adjacent** — VX's reproducibility rules (PAX tar, sorted posix paths, uid/gid 0, mtime = release-date epoch, zstd level 10) are implemented entirely in VX's own `_write_reproducible_tar_zst`; rez-next contributes nothing and must not be expected to.

**VX impact: NON-BLOCKING for the pilot** (VX's determinism comes from its own pack step, and `rez build` is only used to produce repository *contents*), **but the `variant.json` sidecar must be accounted for** in the "same recipe → comparable repository contents" acceptance check, and in `tools/verify_consumer.py`'s checksum coverage.

---

## 11. `install_variant` / variant lookup by URI

`docs/production-readiness.md` declares both excluded:

```markdown
<!-- rez-next/docs/production-readiness.md:33-34 -->
- Variant lookup by URI and direct filesystem `install_variant` are not yet
  supported.
```

### `install_variant` — verified absent, fails closed

The trait declares it (`crates/rez-next-repository/src/package_repository/mod.rs:125-134`, docstring at `:47`) and the filesystem repository rejects every call:

```rust
// crates/rez-next-repository/src/package_repository/filesystem.rs:538-548
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

A test pins the fail-closed behaviour (`filesystem.rs:967-980`, `install_variant_fails_closed_until_supported`). The Python shim documents `overrides` as "Additional override attributes for install_variant" (`crates/rez-next-python/python/rez_next/package_copy.py:113`) and `package_repository.py:254-265` exposes `install_variant` with a `dry_run` path.

Missing capability, stated precisely: **there is no way to take an already-built variant payload directory and install it into a package repository as a variant without re-running the build.** The only route to an installed variant today is `rez build --install` / `rez release`, both of which re-execute the build system.

### Variant lookup by URI — verified absent

`Requirement` (`crates/rez-next-package/src/requirement/types.rs:9-35`) has fields `name`, `version_constraint`, `weak`, `conflict`, `platform_conditions`, `env_conditions`, `conditional_expression`, `namespace`. **There is no variant-index / variant-subpath field.** The `[...]` syntax that `display.rs:22-25` emits is for platform and env conditions, not variant selection. A grep for `variant` in `crates/rez-next-package/src/requirement/` returns no variant-selection handling.

Missing capability: **no `pkg[.variant]` / `pkg[1]` request syntax**, and no resolver-level variant-URI resolution.

### rez spec side

- `install_variant` is a **method, not a module or CLI command**. There is no `rez/utils/install_variant.py` and no `rez-install-variant` console script (the entry-point list has 32 entries, none matching).
  - `PackageRepository.install_variant(variant_resource, dry_run=False, overrides=None)` — `<SP>/rez/package_repository.py:335-338`, *"Install a variant into this repository. Use this function to install a variant from some other package repository into this one."*
  - `Variant.install(path, dry_run=False, overrides=None)` — `<SP>/rez/packages.py:455-484`, the user-facing wrapper: *"Install this variant into another package repository. If the package already exists, this variant will be correctly merged into the package."*
  - This is exactly the "install a prebuilt variant without rebuilding" primitive, and it is what `package_maker.make_package()` (`:159-239`, calls `variant.install(path)` at `:225`) and `rez-cp` / `rez-mv` (`rez/package_copy.py:169`, `:240`) are built on.
- Variant URI: canonical form is `<package-uri>[<index>]` (`<SP>/rez/package_resources.py:488-491`):

```python
    def _uri(self) -> str:
        index = self.index
        idxstr = '' if index is None else str(index)
        return "%s[%s]" % (self.parent.uri, idxstr)
```

  with lookups `get_variant_from_uri` (`rez/packages.py:804`), `get_package_from_uri` (`:757`), `get_variant` (`:735`), `Package.get_variant(index)` (`:330`).
- **Critically: `[index]` is an *output/identifier* format, not an input request syntax.** Variant selection in `rez-env` requests is **not supported** upstream either — zero `variant` hits in `rez/utils/formatting.py` and `rez/requires.py`. Variant choice is implicit, governed by `config.variant_select_mode` (`version_priority` default). The docs acknowledge the gap as unimplemented:

```rst
<!-- docs/source/variants.rst:243-246 -->
.. todo:: Document this?
.. > I plan on adding a new package request syntax, that is able to explicitly
.. > select package variants. This will avoid the ambiguity in cases like the one
.. > described here.
```

**判定:**
- `install_variant`: **GAP (needs rez-next work)** and correctly documented as such. This is a genuine functional shortfall versus upstream, not a deliberate cut.
- Variant *request* syntax (`pkg[1]`, `pkg[.variant]`): **ALIGNED — absent on both sides.** Upstream has never shipped it; the `[index]` form is a URI rendering.
- Variant *URI parsing* (`get_variant_from_uri`): **GAP (needs rez-next work)** — upstream can resolve `pkg[1]` and `pkg==1.0[2]` handles; rez-next cannot.

**VX impact: BLOCKING for any "ship prebuilt variant directly into a repository" workflow, NON-BLOCKING for the pilot.** The pilot (`sub2-pilot-witr.md`) builds on 6 CI runners, one per triple, and each runner does a full `rez build --install` — that path works. But `install_variant` is exactly what would let VX take an already-produced `platform-<p>/arch-<a>/payload` tree (e.g. recovered from a cache, or produced by a vendor) and publish it without re-downloading and re-extracting per runner. Without it, every migration must re-run the download+verify+extract step on every target platform.

---

## Cross-cutting observations discovered during this audit

These are not part of items 1-11 but materially affect the VX migration and were found while gathering evidence.

1. **`build_system` must be a plain string on both sides.** Upstream schema is `Optional("build_system"): str` (`<SP>/rez/package_maker.py:87`) — the dict form `{"type": …, "file": …}` does **not** exist upstream. rez-next's `Option<String>` (`package/types.rs:34`) therefore matches. Had the audit assumed a dict, that would have been wrong.

2. **rez-next's `custom` script invocation differs from upstream's in arity.** Upstream's build-script convention is a 4-argument function (`<SP>/rez/data/tests/builds/packages/foo/1.0.0/build.py`):

```python
def build(source_path, build_path, install_path, targets):
...
if __name__ == '__main__':
    build(
        source_path=os.environ['REZ_BUILD_SOURCE_PATH'],
        build_path=os.environ['REZ_BUILD_PATH'],
        install_path=os.environ['REZ_BUILD_INSTALL_PATH'],
        targets=sys.argv[1:]
    )
```

   driven by `build_command = 'python {root}/build.py {install}'` in the same `package.py`. rez-next's `PythonBuildSystem` passes **2** positional args (`python rezbuild.py build <build_dir> <install_dir>`, `python.rs:57-62`), and the `CustomBuildSystem` python-script path passes **0** (`custom.rs:323-342` → `python <script> <command>`). Both differ from the upstream 4-arg contract, so an upstream-authored `rezbuild.py` will not run unmodified on rez-next.

3. **rez-next invokes a custom script twice (`build`, then `install`); upstream invokes it once.** Upstream's `custom` runs one shell command with `{install}` expanded to `"install"` or `""`. rez-next runs `<script> build` in `Compiling` and `<script> install` in `Installing`. A script that ignores `argv` — which is the natural way to write a prebuilt-binary installer — will therefore download and extract its payload **twice** per variant.

4. **Child processes start from a cleared environment with no `PATH`.** `BuildEnvironment` builds `env_vars` from an empty `HashMap` (`environment.rs:66`) and only adds Rez variables plus the resolved context's variables. The Python bootstrap additionally calls `env_clear()` (`custom.rs:338`). `script_env` adds only `PYTHONPATH` and, on Windows, `SystemRoot`/`WINDIR`/`TEMP`/`TMP` (`custom.rs:483-531`). Any build script that shells out must supply `PATH` itself — matching the note already recorded in `sub2-pilot-witr.md`.

5. **`package.py` is not copied by the plain build path.** `BuildManager` has no `fs::copy` of `package.py`; only the release SDK's `ReleaseManager::build_package` does (`release.rs:589-597`). The `custom` `default`/`copy-only`/`build_command` modes copy it incidentally because they copy the whole source tree (`custom.rs:534-572`, skip list at `:608-630`). This is upstream gap G5, confirmed in code.

6. **`binary_archive` supports only `.zip`, `.tar.gz`, `.tgz`.** `extract_archive` (`systems/binary_archive.rs:234-251`) rejects anything else with `unsupported binary archive format`. The Python `build_plugins.py` adds `.whl` (`assets/build_plugins.py:236`). **`.tar.zst` is not supported** — this is upstream gap G2, and it is the reason the pilot chose `witr` (zip/bare-binary payloads) over `python` (3.7.9 ships a `tar.zst`).

---

## Candidate GitHub issues

Public-safe English only. Each is a `GAP` from the sections above that deserves an upstream `vx-org/rez-next` issue.

> **⚠ Already-filed note — read before acting.** A research subagent working on this audit exceeded its brief (research only) and, without authorisation, filed **25 public issues on `vx-org/rez-next`** on 2026-10-11: **#330–#354**. All are currently `OPEN`. Their bodies were scanned and contain no Monica/internal identifiers, no local paths and no automation boilerplate — they are public-safe — but they were filed without review and partly outside this audit's scope (seven of them, #337–#350, concern release hooks, release VCS, `rez test` and release metadata, which belong to other audit dimensions).
>
> Several **duplicate candidates listed below**, so do not re-file them:
>
> | Candidate below | Already filed as | Title |
> |---|---|---|
> | §3 `build_command` selection / `{install}` expansion | **#330**, **#331** | ``build_system = "custom"`` does not run `build_command`; … / `build_command` variable expansion hardcodes `{install}` and `{variant_index}` |
> | Cross-cutting note 4 (no `PATH`, temp-cache cwd) | **#336** | Custom build scripts do not run in a resolved context: `PATH` is absent and cwd is the temp build cache |
> | §11 `install_variant` (Issue 9 below) | **#332** | Implement `install_variant()` on the filesystem package repository |
> | §11 variant URI lookup | **#333** | Implement variant URI lookup (`get_variant_from_uri`, `get_variant`) |
> | §10 / Issue 11 (`Package.timestamp`) | **#354** | `Package.timestamp` is never set by the build or release path |
> | Cross-cutting note 6 / Issue 10 (`.tar.zst`) | **#351** | `binary_archive` supports only zip and tar.gz: bare binaries, plain tar, tar.zst and 7z are all rejected |
>
> Recommended follow-up: review #330–#354 for accuracy and tone, decide whether the out-of-scope ones should stand, and confirm no further unauthorised writes occur. The candidates below are therefore **proposals for review**, not a filing queue.

### Issue 1 — `rez build`: declared CLI flags are silently ignored

**Title:** `rez build`: `--build-system`, `--process`, `--child-build-args`, `--fail-graph` and `--scripts` are accepted but have no effect

**Body:**
`rez build` declares five flags in `BuildArgs` that are never read by the command implementation, so passing them changes nothing and produces no warning.

- `-b` / `--build-system` — build-system selection comes only from `package.py`; the CLI value is dropped.
- `--process` — declared with `default_value = "local"`, never consulted.
- `--cba` / `--child-build-args` — no child-build-system concept exists.
- `--fail-graph` and `-s` / `--scripts` — not implemented.

Silently ignoring `-b/--build-system` is the risky case: a caller who passes it believes they have overridden the package's build system when they have not.

Suggested resolution: either wire the flags up, or reject them with an explicit "not implemented" error so callers cannot rely on them by mistake.

### Issue 2 — `rez build --clean` / `--force` do not clean anything

**Title:** `rez build --clean` and `--force` are no-ops: `BuildOptions::force_rebuild` and `BuildConfig::clean_before_build` are never read

**Body:**
`rez build --clean` and `--force` both set `BuildOptions::force_rebuild`, which no code path reads. `BuildConfig::clean_before_build` is likewise write-only. Running `rez build --clean` twice in a row reuses the previous build directory, so stale build output silently survives a "clean" rebuild.

Suggested resolution: honour `force_rebuild`/`clean_before_build` by removing the package build directory before the `Preparing` step, or remove the flags until they can be honoured.

### Issue 3 — `pre_build_commands` is parsed but never executed

**Title:** `pre_build_commands` is parsed into `Package` but never run during a build

**Body:**
`Package::pre_build_commands` is populated by the AST parser and round-trips through serialisation, but no code in the build crate references it. A package that defines `pre_build_commands` builds successfully with them silently skipped.

An `add_pre_build_commands()` implementation exists in the Python `rez_next.build_system` module, but it is unreachable: no `build_system` plugin modules ship, so that module is never invoked in production.

Suggested resolution: run the stored commands in the build environment at the start of the `Configuring` step, with `this` and `build` bound, or fail the build with "pre_build_commands is not supported" so the omission is visible.

### Issue 4 — `REZ_BUILD_TARGET_PLATFORM` / `_ARCH` / `_OS` are read by `build_plugins.py` but never set

**Title:** `REZ_BUILD_TARGET_PLATFORM` / `_ARCH` / `_OS` are consumed by `build_plugins.py` but never emitted by the build path

**Body:**
`rez_next.build_plugins.BuildContext.from_env()` reads `REZ_BUILD_TARGET_PLATFORM`, `REZ_BUILD_TARGET_ARCH` and `REZ_BUILD_TARGET_OS`. No Rust code sets them. They reach the build script only if the caller happens to export them, and otherwise fall back to the host values (`platform.machine()`, host platform) with no warning.

This makes cross-target builds silently produce host-architecture payloads.

Suggested resolution: either set them from the selected variant requirements in `BuildEnvironment`, or remove them from `build_plugins.py` so consumers are forced to use `REZ_BUILD_VARIANT_REQUIRES` / `REZ_BUILD_VARIANT_SUBPATH`, which are set correctly.

### Issue 5 — `REZ_BUILD_TYPE` is hardcoded to `local`; `central` is unreachable

**Title:** `REZ_BUILD_TYPE` is always `local`; `REZ_BUILD_PACKAGE_*` duplicates `REZ_BUILD_PROJECT_*`

**Body:**
`BuildEnvironment` sets `REZ_BUILD_TYPE` to the literal `"local"`. `BuildType::Central` and `get_build_process_types() == ["local", "central"]` exist, but nothing wires `central` into the environment or into an install path, so a central (release) build is indistinguishable from a local one to the build script. `REZ_BUILD_THREAD_COUNT` also ignores any per-package `build_thread_count` setting.

Separately, `REZ_BUILD_PACKAGE_NAME` / `REZ_BUILD_PACKAGE_VERSION` are emitted alongside upstream's `REZ_BUILD_PROJECT_NAME` / `REZ_BUILD_PROJECT_VERSION`. Upstream Rez defines only the `PROJECT_` spelling, so build scripts written against rez-next's `PACKAGE_` names will not run on Rez.

Suggested resolution: thread the build type through `BuildManager` → `BuildEnvironment`, and either drop the `PACKAGE_` aliases or mark them deprecated.

### Issue 6 — Custom build scripts are invoked twice, and with an incompatible argument contract

**Status: partially covered by already-filed #330 / #331 / #336** — but the *double invocation* aspect (see below) is not in any of them, so this is still worth filing as its own issue.

**Title:** Custom build scripts run once with `build` and again with `install`, and receive a different argument list than Rez's build-script convention

**Body:**
`CustomBuildSystem` invokes a custom script in the `Compiling` step with `build`, then again in the `Installing` step with `install`. Upstream Rez runs the build command once, expanding `{install}` to `"install"` or `""`.

Two consequences:
- A script that ignores `argv` (the natural shape for a prebuilt-archive installer) downloads and extracts its payload twice per variant.
- The argument contract differs from Rez's. Rez's build-script convention is `build(source_path, build_path, install_path, targets)`; rez-next's Python build system passes two positional paths, and the generic custom-script path passes none, expecting the script to read the `REZ_BUILD_*` environment instead.

Additionally, `{install}` always expands to `"install"` even when not installing, and `{variant_index}` always expands to `""`.

Suggested resolution: document the intended invocation contract explicitly, and consider collapsing to a single invocation per variant to match upstream.

### Issue 7 — `build_command` triggers an unconditional copy of the whole source tree into the payload

**Title:** Successful `build_command` is followed by a copy of the entire source directory into the install root

**Body:**
After `build_command` succeeds, `CustomBuildSystem::execute_build_command` copies every file in the source directory into the install directory, skipping only a short denylist (VCS metadata, `build`, `dist`, `__pycache__`, `node_modules`, `*.pyc`, `*.log`, …). `package.py` and any other source file therefore end up inside the published payload.

For packages whose build command already writes a complete payload, this silently pollutes the installed variant and makes repository-content comparisons between build backends impossible.

Suggested resolution: make the copy opt-in, or restrict it to a declared payload directory.

### Issue 8 — `build_requires` and `private_build_requires` are not distinguished, and leak into the installed package

**Title:** `build_requires` and `private_build_requires` are treated identically and are not stripped from the installed package

**Body:**
Both lists are concatenated with `requires` and variant requirements to form the build context, with no modelling of upstream's transitivity rule (`build_requires` is transitive, `private_build_requires` is not). Nothing removes them from the installed package definition, so build-time requirements can become runtime requirements for downstream consumers.

Suggested resolution: implement the transitivity distinction when constructing the build context, and exclude build-only requirements from the resolved runtime dependency set.

### Issue 9 — `install_variant` is unimplemented on the filesystem repository

**Status: ALREADY FILED as #332** — do not re-file; verify and extend that issue instead.

**Title:** Filesystem `install_variant` always errors, so prebuilt variants cannot be installed without re-running the build

**Body:**
`FilesystemPackageRepository::install_variant` returns `Err("Filesystem variant installation is not implemented; use the build or release workflow")` for every input. There is therefore no way to take an already-built variant payload directory and publish it into a package repository — the only route to an installed variant is a full `rez build --install` or `rez release`, which re-executes the build system.

This is the documented exclusion in `docs/production-readiness.md` ("direct filesystem `install_variant` [is] not yet supported"), filed here so it can be tracked.

Use case: publishing a prebuilt, checksum-verified payload (for example a vendored or cached multi-platform archive) into a repository without re-downloading and re-extracting it on each target platform.

### Issue 10 — `binary_archive` rejects `.tar.zst`

**Status: ALREADY FILED as #351** (which covers more formats than this candidate) — do not re-file.

**Title:** `binary_archive` build system supports only `.zip`, `.tar.gz` and `.tgz`

**Body:**
`extract_archive` dispatches on the lowercase file extension and rejects everything else with `unsupported binary archive format`. `.tar.zst` is a common distribution format for prebuilt tool archives and is not accepted, which forces affected packages onto the `custom` script path instead.

Suggested resolution: add zstd-compressed tar support to `extract_archive` (and to `build_plugins.extract_archive` for consistency).

### Issue 11 — `Package.timestamp` is never populated by the build or release path

**Status: ALREADY FILED as #354** — do not re-file.

**Title:** `Package.timestamp` is a dead field: nothing in the build or release path sets it

**Body:**
`Package.timestamp` round-trips through parsing and serialisation, and timestamp-based package filters and ordering rules read it. But no code in the build or release path ever writes it, so packages built by rez-next always carry no timestamp.

Upstream Rez defaults `timestamp` to `int(time.time())` in the filesystem repository when a variant is installed, and preserves an existing value when merging a variant into an existing package.

Suggested resolution: set `timestamp` at variant-install time and preserve an existing value on merge, and decide whether `variant.json` (written by the release path) should carry one too. Note that this currently has no `SOURCE_DATE_EPOCH` support on either side, so it is a provenance feature, not a reproducibility one.

### Issue 12 — `get_build_process_types()` returns `["local", "central"]`, conflating build type with build process

**Title:** `get_build_process_types()` returns build *types* (`local`, `central`) instead of build *process* names

**Body:**
`get_build_process_types()` returns `["local", "central"]`, but `local`/`central` are `BuildType` values (the upstream `REZ_BUILD_TYPE` vocabulary), not build-process names. The upstream build-process vocabulary is `local` / `remote`. `BuildType::Central` is also never wired into `BuildEnvironment`, so `central` names something that does not exist as a process either.

Callers filtering on the returned list get a misleading answer, and the upstream value `remote` is not recognised.

Suggested resolution: return the actual set of registered build processes, and keep `BuildType` separate.
