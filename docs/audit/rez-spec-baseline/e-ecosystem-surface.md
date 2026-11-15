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

