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
            "to force the release" % self.package.version
        )
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

