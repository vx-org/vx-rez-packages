# Audit 02 — TEST + RELEASE dimensions (rez-next vs upstream Rez)

## Scope and method

Evidence-gathering only. No code was modified in any repository.

| Item | Value |
| --- | --- |
| `rez-next` under audit | `rez-next/` worktree, HEAD `97eef03928012d540f45d25fa82553da123e8786` (2026-10-10), version `0.3.10` (`.release-please-manifest.json`) |
| Upstream Rez reference | `AcademySoftwareFoundation/rez`, branch `main`, commit `f622b817ef635223ca904a4e745d23e709738936` (full source tree downloaded and grepped locally) |
| rez spec side notation | upstream paths are relative to the upstream repo root, e.g. `src/rez/package_test.py:22` |
| rez-next side notation | paths are relative to the `rez-next/` worktree root, e.g. `crates/rez-next-build/src/release.rs:287` |

Where a claim could not be verified against upstream source it is marked
`upstream-side: UNVERIFIED (reason)`. No upstream path is invented.

### Upstream premises that this audit could NOT confirm

Two premises in the audit brief do not correspond to anything in upstream Rez.
Both were checked against the **complete upstream source tree**, not by search engine:

1. **`package_test.py` with `rez:test` / `rez:setup` / `rez:teardown` decorated runner functions, and pytest/unittest runner auto-detection.**
   - Command: `grep -rn "rez:test\|rez:setup\|rez:teardown" <upstream-tree> --include=*.py --include=*.md` → **0 hits**.
   - Command: `find <upstream-tree> -name "package_test*"` → **1 hit**: `src/rez/package_test.py`, which is the *runner library*, not a per-package test file.
   - `upstream-side: NOT PRESENT`. Upstream `rez test` runs the `tests` **dict attribute** declared in `package.py` (`src/rez/package_test.py:22-51`). There is no per-package `package_test.py` convention, no decorator protocol, and no pytest/unittest auto-detection anywhere in upstream Rez.
   - The same convention is also absent from the VX workspace: `grep -rn "rez:test" <worktree>` (excluding `rez-next/`) → 0 hits.
   - **Conclusion:** `package_test.py` / `rez:test` is not a Rez spec feature. It is neither implemented in rez-next nor specified upstream. It is reported below as a VX-side convention with zero implementation on both sides, not as a rez-next regression.

2. **Upstream `release_hook` plugins `github_repository` and `slack`.**
   - Command: `find <upstream-tree>/src -path "*release_hook*" -name "*.py"` → `src/rez/release_hook.py`, `src/rezplugins/release_hook/__init__.py`, `amqp.py`, `command.py`, `emailer.py`, `rezconfig.py`.
   - `upstream-side: NOT PRESENT`. Upstream ships exactly **three** hook plugins: `amqp`, `command`, `emailer`.

---

# TEST

## T1. `rez test` — implemented in rez-next? CLI surface?

**Evidence (rez-next):** registered as a first-class subcommand.

- `src/cli/mod.rs:63-64`
  ```rust
  /// Run tests defined in a package
  Test(commands::test::TestArgs),
  ```
- `src/cli/mod.rs:242` — `RezCommand::Test(args) => commands::test::execute(args.clone()),`
- `src/cli/commands/test.rs:25-69` — `TestArgs`: `PKG`, `TEST...`, `-l/--list`, `--inplace`,
  `--extra-packages`, `--paths`, `--no-local`, `--dry-run`, `--stop-on-fail`, `-v/--verbose`, `-w/--working-dir`.

**rez spec side:** `src/rez/cli/test.py:11-44` — upstream `rez test` exposes
`-l/--list`, `--dry-run`, `-s/--stop-on-fail`, `--inplace`, `--extra-packages` (`nargs='+'`),
`--paths`, `--nl/--no-local`, `PKG`, `TEST...`.

**Flag-level comparison:**

| Upstream flag | rez-next | 判定 |
| --- | --- | --- |
| `PKG` positional | `PKG` (test.rs:26-28) | ALIGNED |
| `TEST...` positional | `TEST...` (test.rs:31-32) | ALIGNED |
| `-l`, `--list` | present (test.rs:35-36) | ALIGNED |
| `--dry-run` | present (test.rs:55-56) | ALIGNED |
| `-s`, `--stop-on-fail` | `--stop-on-fail` only — **no `-s` short form** (test.rs:59-60) | INTENTIONAL DEVIATION (cosmetic) |
| `--inplace` | present (test.rs:39-40) | ALIGNED |
| `--extra-packages` | present (test.rs:43-44) | ALIGNED (name and semantics) |
| `--paths` | present (test.rs:47-48) | ALIGNED |
| `--nl`, `--no-local` | `--no-local` only — **no `--nl`** (test.rs:51-52) | INTENTIONAL DEVIATION (cosmetic) |
| *(none)* | `-v/--verbose` (test.rs:63-64) | INTENTIONAL DEVIATION (addition; upstream hardcodes `verbose=2` at `src/rez/cli/test.py:83`) |
| *(none)* | `-w/--working-dir` (test.rs:67-68) | INTENTIONAL DEVIATION (addition) |
| extra args after `--` forwarded to a single test (`src/rez/cli/test.py:67-73`) | **absent** | GAP |
| `--inplace` + others mutual exclusion (`src/rez/cli/test.py:54-58`) | present (test.rs:661-666) | ALIGNED |

**判定:** **ALIGNED** for `rez test` existence and core flag surface.
**VX impact:** NON-BLOCKING — `rez test` exists and resolves a real environment
(`src/cli/commands/test.rs:272-341`), which is the substantive part.

---

## T2. `package_test.py` — discovery, runner functions, test-runner detection

### T2a. Per-package `package_test.py` / `rez:test` convention

**Evidence (rez-next):** absent. `crates/rez-next-python/python/rez_next/package_test.py:14-22`
is a **re-export shim** of the native module, not a discovery mechanism:

```python
from ._native.test import (  # type: ignore[import]
    ERROR,
    FAILED,
    SKIPPED,
    SUCCESS,
    PackageTestResults,
    PackageTestRunner,
)
```

There is no filesystem lookup for a `package_test.py` next to the package definition anywhere
in the tree.

**rez spec side:** `upstream-side: NOT PRESENT` — see "Upstream premises that this audit could NOT confirm", item 1.

**判定:** **INTENTIONAL DEVIATION (no-op)** — the brief's premise is not a Rez feature.
**VX impact:** BLOCKING **if and only if** VX packages rely on a `package_test.py` +
`rez:test` convention. Since that convention is VX-local and implemented on neither side,
the correct action is a VX-side decision (drop the convention, or specify and implement it),
**not** a rez-next spec-compliance bug. Flagged for product decision.

### T2b. Does rez-next find and run the `tests` attribute?

Yes, in **two** places, with materially different capability:

| Path | What it reads | Env resolved? | Variants? |
| --- | --- | --- | --- |
| CLI `rez-next test` — `src/cli/commands/test.rs:233-246` | `package.tests` (`HashMap<String,String>`) | **Yes** (solver + `EnvironmentManager`, test.rs:272-341) | Partial (requirement sets per variant, test.rs:608-641) |
| Python `rez_next.package_test.PackageTestRunner` — `crates/rez-next-package/src/package/test_runner.rs:191-216` | `package.tests` | **No** | No |
| Build pipeline `BuildStep::PackageTesting` — `crates/rez-next-build/src/process.rs:556-626` | `package.tests` | Yes (resolved env) | No |

**Critical divergence — the Python-facing runner is not usable for real packages.**
`crates/rez-next-package/src/package/test_runner.rs:114-131` and `:162-188`:

```rust
pub fn new(package_spec: String) -> RezCoreResult<Self> {
    let working_dir = std::env::current_dir().map_err(RezCoreError::from)?;
    ...
    runner.load_test_definitions(&working_dir, &package_spec)?;
```
```rust
// Try to find package.py or package.yaml in working_dir
let candidates = [working_dir.join("package.py"), ...];
for candidate in &candidates {
    if candidate.exists() && let Ok(package) = PackageSerializer::load_from_file(candidate) {
        self.extract_tests_from_package(&package);
        return Ok(());
    }
}
// If not found in working_dir, try configured package paths
// (This would require access to RezCoreConfig)
// For now, just return Ok with empty test_definitions
Ok(())
```

The `package_spec` argument is **unused** (`_package_spec`, line 165) — the "package to test"
is silently ignored; only the current working directory is searched. Compare upstream
`src/rez/package_test.py:130-137`, which resolves the request through the package search path:

```python
package = get_latest_package_from_string(str(self.package_request), self.package_paths)
if package is None:
    raise PackageNotFoundError("Could not find package to test: %s" % str(self.package_request))
```

The Python runner also executes with **no resolved environment**
(`crates/rez-next-package/src/package/test_runner.rs:396-401`):

```rust
let result = Command::new(&program)
    .args(&args)
    .current_dir(&self.working_dir)
    .stdout(Stdio::piped())
    .stderr(Stdio::piped())
    .output();
```
(no `.envs(...)` — contrast the CLI path at `src/cli/commands/test.rs:512-514`, which does
`command.env_clear().envs(environment);`)

**rez spec side:** `src/rez/package_test.py:252-502` — upstream resolves a `ResolvedContext`
per test (`_get_context`, line 586) and executes via `context.execute_shell(...)`
(line 463-469) so the test runs inside a fully activated rez environment.

**判定:** **GAP (needs rez-next work)** for the Python `PackageTestRunner`.
**VX impact:** BLOCKING for any Python consumer of `rez_next.package_test`
(the documented drop-in for `rez.package_test`, per the module docstring at
`crates/rez-next-python/python/rez_next/package_test.py:1-10`). The CLI is fine; the Python API is not.

### T2c. Runner functions (`rez:test` / `rez:setup` / `rez:teardown`)

**Evidence (rez-next):** no occurrence of `rez:test`, `rez:setup`, or `rez:teardown` anywhere.
Command: `grep -rn '"rez:test"\|rez:setup\|rez:teardown' --include=*.rs --include=*.py --include=*.toml rez-next/` → 0 hits.

**rez spec side:** `upstream-side: NOT PRESENT` (see premise item 1).

**判定:** INTENTIONAL DEVIATION / N-A — not a Rez feature on either side.

### T2d. Test-runner detection (pytest / unittest)

**Evidence (rez-next):** no detection logic. Tests are opaque shell strings; whatever the
string invokes is what runs. `src/cli/commands/test.rs:480-500` and
`crates/rez-next-package/src/package/test_runner.rs:370-390` shell out (`sh -c` / `cmd /c`) or
exec the argv directly.

**rez spec side:** upstream also does **no** runner detection — `src/rez/package_test.py:312`
(`command = test_info["command"]`) and `:463` (`context.execute_shell(command=command, ...)`).
`pytest`/`unittest` appear only inside the user-authored command strings in the docstring
example (`src/rez/package_test.py:31-38`).

**判定:** **ALIGNED**.
**VX impact:** NON-BLOCKING.

---

## T3. `--extra-package` and extra requires for tests

**CLI surface:** `src/cli/commands/test.rs:42-44`

```rust
/// Extra packages to add to test environment
#[arg(long = "extra-packages")]
pub extra_packages: Vec<String>,
```

Wired into the resolve at `src/cli/commands/test.rs:608-641`:

```rust
let base: Vec<_> = package.requires.iter().chain(args.extra_packages.iter()).cloned().collect();
if package.variants.is_empty() {
    vec![base]
} else {
    package.variants.iter().map(|variant| base.iter().cloned().chain(variant.iter().cloned()).collect()).collect()
}
```

and enforced as mutually exclusive with `--inplace` at `src/cli/commands/test.rs:661-666`.

**rez spec side:** `src/rez/cli/test.py:26-28` declares `--extra-packages` (plural), and
`src/rez/package_test.py:566-568` appends them to every test's request:

```python
if self.extra_package_requests:
    reqs = map(str, self.extra_package_requests)
    requires.extend(reqs)
```

**Per-test `requires` (the `tests` dict form):** **not supported in rez-next.** See T4/T5.

**判定:** **ALIGNED** for the CLI flag. **GAP** for per-test `requires` (covered in T4).
**VX impact:** NON-BLOCKING for the CLI flag; BLOCKING for per-test requires (T4).

---

## T4. The `tests` dict in `package.py` — dict / list entries

This is the single largest TEST-dimension gap.

**Evidence (rez-next) — type is string-only:**
`crates/rez-next-package/src/package/types.rs:44`
```rust
pub tests: HashMap<String, String>,
```

**Evidence (rez-next) — non-string values are a hard parse error:**
`crates/rez-next-package/src/python_ast_parser/extract.rs:140-177`
```rust
pub(super) fn extract_tests(&self, expr: &Expr) -> Result<HashMap<String, String>, RezCoreError> {
    match self.evaluate_expression(expr) {
        Ok(PythonValue::Dict(dict)) => {
            for (key, value) in dict {
                let value_str = match value {
                    PythonValue::String(s) => s,
                    _ => {
                        return Err(RezCoreError::PackageParse(format!(
                            "Unsupported test definition for '{key}': only string commands are supported"
                        )));
                    }
                };
                ...
```

This is the code path reached by `PackageSerializer::load_from_file`
(`crates/rez-next-package/src/serialization/load.rs:62-65` → `load_from_file_with_options` →
`PackageFormat::Python` → `load_from_python`), i.e. **the only** `package.py` loader.

**Evidence (rez-next) — the per-test fields exist but are never populated:**
`src/cli/commands/test.rs:232-246`
```rust
// Package.tests is HashMap<String, String> where value is the command
for (test_name, command_str) in &package.tests {
    let cmd = TestCommand::String(command_str.clone());
    self.test_definitions.insert(test_name.clone(), TestDefinition {
        name: test_name.clone(),
        command: cmd,
        requires: vec![],
        run_on: vec!["default".to_string()],
        on_variants: None,
    });
}
```
`requires`, `run_on`, `on_variants` are hardcoded. Identical hardcoding in
`crates/rez-next-package/src/package/test_runner.rs:205-214`.

**rez spec side:** `src/rez/package_test.py:27-51` (docstring) and `:542-584` (`_get_test_info`):
```python
tests = {
    "unit": "python -m unittest -s {root}/tests",
    "CI": {"command": "python {root}/ci_tests/main.py", "requires": ["maya-2017"], "replace": True},
}
```
```python
    test_entry = tests_dict.get(test_name)
    if not test_entry:
        return None
    if not isinstance(test_entry, dict):
        test_entry = {"command": test_entry}
    ...
    return {
        "command": test_entry["command"],
        "requires": requires,
        "run_on": run_on,
        "on_variants": test_entry.get("on_variants", False),
    }
```
Upstream accepts **string, list of argv, or dict** (`src/rez/package_test.py:49-51`:
"Commands can also be a list - in this case, the test process is launched directly, rather than
interpreted via a shell"). Dict keys: `command`, `requires`, `run_on`, `on_variants`
(`on_variants` may itself be a filter dict, handled at `src/rez/package_test.py:329-349`).

**判定:** **GAP (needs rez-next work).**
**VX impact:** **BLOCKING.** Any VX package that uses the dict or list form of `tests`
fails at **package parse time** — the whole `package.py` becomes unloadable, which breaks
`rez test`, `rez build`, `rez release`, and every resolve that touches the package. This is
worse than "the test is skipped": the package becomes invisible to the toolchain.

---

## T5. Post-install tests (the `tests` dict run after install)

**Evidence (rez-next):** the build pipeline has a dedicated post-install test step.

`crates/rez-next-build/src/process.rs:39-56` — step order:
```rust
pub enum BuildStep {
    Preparing, Configuring, Compiling, Testing, Packaging, Installing,
    /// Running tests declared by the installed package
    PackageTesting,
    Cleaning up -> Cleanup,
}
```
`crates/rez-next-build/src/process.rs:288-296` — execution order is exactly that enum order,
so `PackageTesting` runs **after** `Installing`.

`crates/rez-next-build/src/process.rs:556-626` — `execute_package_test_step`:
- skips when `request.package.tests.is_empty()` (line 560-562)
- appends `pre_test_commands` to `post_commands` (line 572-577)
- builds an environment via `EnvironmentManager` (line 587-594)
- substitutes only four tokens (line 604-608):
  ```rust
  let command = command
      .replace("{this.root}", &root).replace("{this.base}", &root)
      .replace("{root}", &root).replace("{base}", &root);
  ```
- runs with `ShellExecutor` (line 595-597, 610)
- returns `(false, output, errors)` on the first failing test (line 612-623)

Also reachable from `rez-next build --skip-tests` off / on (`src/cli/commands/build.rs:90`,
gated at `crates/rez-next-build/src/process.rs:425-432`).

**rez spec side:** upstream runs package tests **before** the package definition is published,
and rolls back on failure.
- `src/rezplugins/build_process/local.py:427-441` (`_release_variant`):
  ```python
  # run any tests that are configured to run pre-install
  try:
      self._run_tests(
          variant, run_on=["pre_release"], package_install_path=build_result["package_install_path"]
      )
  except PackageTestError:
      # delete the installed variant payload
      self._rmtree(build_result["variant_install_path"])
      # indicate to repo that the variant install is cancelled
      cancel_variant_install()
      raise
  ```
- `src/rezplugins/build_process/local.py:372-387` (`_build_variant`) — same pattern with
  `run_on=["pre_install"]`.
- Ordering documented at `src/rezplugins/build_process/local.py:449-461`.
- Selection by tag: `src/rezplugins/build_process/local.py:465-469` uses
  `PackageTestRunner.get_package_test_names(package=..., run_on=run_on, ran_once=...)`,
  i.e. `run_on` filtering is **load-bearing** upstream.
- Token expansion uses full object formatting: `src/rez/package_test.py:412-418`
  (`command = variant.format(command)`), not a fixed 4-token replace.

**判定:** **GAP (needs rez-next work)** on two axes:
1. Ordering — rez-next tests **post**-install; upstream tests **pre**-install and rolls back.
   Combined with the absence of rollback (R1 below), a failing test leaves a released payload
   on disk.
2. `run_on` filtering is absent, so there is no way to express "run these before publishing,
   those after".

**VX impact:** BLOCKING. Post-install-only testing plus no rollback means a broken package can
become visible to consumers before its tests have run.

---

## T6. Test result model / exit-code semantics

**Evidence (rez-next) — four statuses:**
`crates/rez-next-package/src/package/test_runner.rs:22-32`
```rust
pub enum TestStatus { Success, Failed, Skipped, Error }
```
`TestResult` (`:66-81`) carries `name`, `status`, `output`, `error`, `duration_ms`,
`exit_code: i32`, `variant: Option<String>`.
Python constants: `crates/rez-next-python/src/test_bindings.rs:261-264`
```rust
m.setattr("SUCCESS", "success")?;
m.setattr("FAILED", "failed")?;
m.setattr("SKIPPED", "skipped")?;
m.setattr("ERROR", "error")?;
```

**rez spec side — three statuses:**
`src/rez/package_test.py:684`
```python
valid_statuses = ("success", "failed", "skipped")
```
`add_test_result` (`:713-722`) raises `RuntimeError("Invalid status")` for anything else.
Record shape (`:717-722`): `test_name`, `variant`, `status`, `description`.

**Exit-code semantics:**

| Behaviour | rez-next | Upstream |
| --- | --- | --- |
| CLI exit | `std::process::exit(exit_code)` — `src/cli/commands/test.rs:722-724` | `sys.exit(exitcode)` — `src/rez/cli/test.py:121` |
| Value on failure | first non-zero test return code (`src/cli/commands/test.rs:709-711`) | first non-zero return code (`src/rez/cli/test.py:114-115`) |
| "could not run" sentinel | `-1` (`src/cli/commands/test.rs:415`, `test_runner.rs:306`) | `-1` (`src/rez/package_test.py:385`, `:484`) |
| Env-resolve failure | `-1` at `src/rez/package_test.py:385`; in rez-next the resolve error propagates as `Err` from `extract_tests_from_package` (`src/cli/commands/test.rs:313-320`) | — |
| No tests found | prints and returns `Ok(())` → exit 0 (`src/cli/commands/test.rs:674-678`) | `sys.exit(0)` (`src/rez/cli/test.py:89-91`) |
| Empty match set | exit 0 (`src/cli/commands/test.rs:700-703`) | `sys.exit(0)` (`src/rez/cli/test.py:102-107`) |

**判定:** **ALIGNED** on exit-code semantics. **INTENTIONAL DEVIATION** on the status set
(rez-next adds a 4th `error` state). Consequence: code written against upstream that asserts
`status in ("success","failed","skipped")` still works; code that round-trips rez-next
`ERROR` into upstream `PackageTestResults.add_test_result` will raise
`RuntimeError("Invalid status")` (`src/rez/package_test.py:714-715`).

**VX impact:** NON-BLOCKING.

---

# RELEASE

## R0. Cross-cutting finding: three divergent release implementations

This must be stated before any per-question answer, because "which phases does rez-next run"
has three different correct answers depending on the entry point.

| # | Implementation | Entry point | Real build? | Hooks? | Changelog? | Tag format | Push? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | `ReleaseManager::release_with_vcs` | Rust SDK / `rez_next._native.release` | **No** — dirs + copy `package.py` only | No | Yes (step 6) | `{name}-{version}` | No |
| B | `commands::release::execute` | `rez-next release` (CLI) | **Yes** — `BuildManager` per variant | No | No | `{name}-{version}` | **Yes** (`git push origin <tag>`) |
| C | `BuildProcessHelper.release` | `rez_next.build_process` (Python) | Yes (delegates to build system) | `run_hooks()` defined but **never called** | Yes | **`v{version}`** | No |

**Evidence for A:** `crates/rez-next-build/src/release.rs:287` (`release_with_vcs`), with
`build_package` at `:516-600` performing only directory creation, `variant.json` writes, and
`fs::copy(package.py)` (`:590-597`). No build command is executed anywhere in that function.

**Evidence for B:** `src/cli/commands/release.rs:66-182`; the variant loop at `:135-164`
calls `build_manager.start_build` / `wait_for_build`.

**Evidence for C:** `crates/rez-next-python/python/rez_next/build_process.py:382-396`.

**Evidence that B does not use A:** `grep -rn "ReleaseManager\|release_with_vcs\|ReleaseMode"
--include=*.rs src/` → **0 hits**. The CLI release command never touches `ReleaseManager`;
it reimplements tag checking, VCS detection and tagging with direct `git` subprocess calls.

**Evidence that C never fires hooks:** `grep -n "run_hooks"
crates/rez-next-python/python/rez_next/*.py` → 3 hits, all inside the definition of
`run_hooks` itself (`build_process.py:306`, `:309`, `:311`). `release()`
(`build_process.py:382-396`) calls `pre_release()`, `build()`, `post_release()` — **no
`run_hooks` call**.

**判定:** **GAP (needs rez-next work)** — architectural.
**VX impact:** BLOCKING. VX cannot reason about "what does rez-next do on release" without
picking one path, and the paths disagree on tag format, push behaviour, and whether a build
happens at all.

---

## R1. Release phase semantics and rollback

### Path A — `ReleaseManager::release_with_vcs` (`crates/rez-next-build/src/release.rs:287-405`)

Documented order at `crates/rez-next-build/src/release.rs:211-221`:
```
/// 1. Load and validate the package definition
/// 2. Detect and validate VCS repository state
/// 3. Reject an already-released version (tag policy check, fails fast)
/// 4. Build the package (including variants)
/// 5. Run the package tests
/// 6. Generate the changelog
/// 7. Write release metadata
/// 8. Install the package
/// 9. Create the VCS tag
```

| Step | Code | On failure |
| --- | --- | --- |
| 1 | `:295-299` — `load_package`; errors → `return Ok(result)` | abort, nothing written |
| 2 | `:307-330` — `validate_repo_state()` then `get_metadata()`; validation error → `return Ok(result)` (`:312-313`); metadata error → warning only (`:317-320`) | abort on validation; degrade on metadata |
| DryRun | `:333-340` — sets `success = true` unconditionally and returns | n/a |
| 3 | `:351-359` — `check_existing_tag`; `Some(false)` pushes an error → `return Ok(result)` (`:356-359`) | abort before build |
| 4 | `:361-364` — `build_package`; errors recorded, **execution continues** | **no abort, no rollback** |
| 5 | `:366-373` — `run_tests`; errors recorded, **execution continues** | **no abort, no rollback** |
| 6 | `:375-378` — `generate_changelog`; error → warning only (`:722-726`) | continue |
| 7 | `:380-381` — `write_release_metadata`; write failure → warning only (`:750-760`) | continue |
| 8 | `:383-384` — `install_package_definition`; copy error → error **and** `Err` (`:800-805`) | error recorded, `Err` returned |
| 9 | `:396-401` — `create_vcs_tag`, guarded by `result.errors.is_empty() && !tag_pre_existed` | error recorded |
| final | `:403` — `result.success = result.errors.is_empty();` | — |

**Rollback: none.** Steps 4 and 5 do not check `result.errors` before continuing, so a build
or test failure still reaches steps 7 and 8 — directories are created
(`crates/rez-next-build/src/release.rs:532-537`), `variant.json` files written (`:565-568`),
`package.py` copied (`:590-597`), `vcs_metadata.json` written (`:744-747`), and the package
definition re-copied (`:798-806`). Only the **tag** is suppressed. Nothing is deleted or
undone. The doc's invariant (`docs/release-sdk.md:139`) — *"tag exists ⟺ release succeeded"* —
holds, but the stronger property a consumer actually needs — *"a failed release leaves no
installed package behind"* — does not.

**Release-path test execution is also semantically wrong.**
`crates/rez-next-build/src/release.rs:861-912` (`get_test_commands`) imports `tests` from
`package.py` and **calls it as a function**, expecting a JSON array of strings:

```rust
try:
    from package import tests
    commands = tests()
    print(json.dumps(commands))
except ImportError:
    print("[]")
except Exception as e:
    print("[]")
```

Upstream `tests` is a **dict attribute**, not a callable. Since the loader
(`extract.rs:140-178`) can only produce `HashMap<String, String>`, `tests()` would raise
`TypeError: 'dict' object is not callable`, which the `except Exception` swallows into `"[]"`
— so release-path tests **silently never run**. The warning emitted is
`"No test commands found in package.py::tests()"` (`release.rs:826-828`), which reads as
"package has no tests" rather than "test discovery is broken".

Additionally, release-path tests run with `current_dir(install_path)`
(`crates/rez-next-build/src/release.rs:920-935`) and **no resolved environment**, and
`--extra-packages` / `requires` / `run_on` are unavailable.

### Path B — CLI `rez-next release` (`src/cli/commands/release.rs:66-182`)

| Phase | Code | On failure |
| --- | --- | --- |
| load package | `:77-84` | `Err` |
| detect VCS | `:87-95`, `detect_vcs` at `:230-240` | — |
| reject non-git | `:91` → `ensure_supported_vcs` at `:242-249` | `Err` |
| validate repo state | `:98-100` → `:266-299` (`git status --porcelain`; unpushed check is warning-only, `:289-296`) | `Err` |
| existing-tag check | `:103-111` | `Err` |
| dry-run return | `:113-118` | n/a |
| build variants | `:120-164` | `Err` on first failed variant (`:157-163`) — **payload already installed, not rolled back** |
| tag + push | `:168-178` → `:312-361` | `Err` |

**Partial rollback exists here, and only here:**
`src/cli/commands/release.rs:336-358`
```rust
let push = Command::new("git").args(["push", "origin", tag]).current_dir(working_dir).output()
    .map_err(|error| {
        let _ = Command::new("git").args(["tag", "-d", tag]).current_dir(working_dir).output();
        RezCoreError::BuildError(format!("Failed to push tag '{tag}': {error}"))
    })?;

if !push.status.success() {
    let stderr = String::from_utf8_lossy(&push.stderr);
    let _ = Command::new("git").args(["tag", "-d", tag]).current_dir(working_dir).output();
    return Err(RezCoreError::BuildError(format!("Failed to push tag '{tag}' to origin: {}", stderr.trim())));
}
```
A failed push deletes the local tag. **A failed build or a failed test does not undo the
install** — the build loop `Err`s at `:157-163` after `wait_for_build` has already installed
the variant.

### Path C — Python `BuildProcessHelper.release` (`build_process.py:382-396`)

```python
def release(self, release_message=None, variants=None):
    if self._build_system is None:
        raise BuildProcessError("No build system configured for release")
    ...
    self.pre_release()
    build_count = self.build(install=True, variants=variants)
    if build_count == 0:
        raise ReleaseError("Build failed: no variants were built successfully")
    tag_name = self.post_release(release_message=release_message)
```
No rollback, no hooks, no changelog written into the package.

### rez spec side — canonical upstream order

`src/rezplugins/build_process/local.py:90-147` (`LocalBuildProcess.release`):

1. `pre_release()` — `src/rez/build_process.py:301-347`:
   release path exists (`:306-307`) → `vcs.validate_repostate()` (`:313`) →
   tag-exists check, gated on `release_settings.check_tag and not self.ignore_existing_tag`
   (`:316-326`) → UUID match against the previous release (`:333-337`) →
   `ensure_latest` check (`:340-347`)
2. `get_release_data()` → `changelog`, `previous_version`, `previous_revision`
   (`:97-100`; `src/rez/build_process.py:414-448`)
3. **`run_hooks(ReleaseHookEvent.pre_release, ...)`** (`:103-109`)
4. `visit_variants(self._release_variant, ...)` (`:112-115`), and per variant
   (`src/rezplugins/build_process/local.py:394-447`):
   a. dry-run install → skip if destination variant already exists (`:398-404`)
   b. `_build_variant_base(clean=True, install=True)`; on `BuildError` →
      `cancel_variant_install()` + `raise` (`:414-425`)
   c. `_run_tests(run_on=["pre_release"], ...)`; on `PackageTestError` →
      **`self._rmtree(build_result["variant_install_path"])`** +
      `cancel_variant_install()` + `raise` (`:428-441`)
   d. `variant.install(release_path, overrides=release_data)` (`:446`)
5. **`run_hooks(ReleaseHookEvent.post_release, ...)`** (`:122-128`)
6. `post_release()` → `vcs.create_release_tag(tag_name, message)`, guarded by
   `if released_variants:` (`:131-132`; `src/rez/build_process.py:349-357`)

**Upstream rollback is real and payload-level:** `src/rezplugins/build_process/local.py:434-441`
deletes the installed payload directory and notifies the package repository
(`pkg_repo.on_variant_install_cancelled(variant.resource)`, `:406-408`). Upstream also
engineers the ordering so tests run *before* the package definition is published
(`src/rezplugins/build_process/local.py:449-461`).

**判定:** **GAP (needs rez-next work).**
- Step-3-before-build tag check: **ALIGNED** (better than upstream, which defaults
  `check_tag = False`).
- Tag-last: **ALIGNED**.
- **No rollback on build/test failure: GAP.**
- **Hooks absent from the phase list: GAP** (see R2).
- Release-path test discovery is broken: **GAP**.

**VX impact:** BLOCKING. VX releases pre-built assets; a release whose tests fail must not
leave a published payload behind.

---

## R2. `release_hook` plugin family

### Does rez-next have a hook plugin system?

Yes — a Rust one, plus a Python shim. **It is never invoked by any release path.**

**Registry:** `crates/rez-next-release-hook/src/registry.rs:15-18, 89-95`
```rust
pub struct ReleaseHookRegistry { hooks: Mutex<HashMap<String, HookFactory>>, }
static GLOBAL_REGISTRY: std::sync::OnceLock<ReleaseHookRegistry> = std::sync::OnceLock::new();
pub fn get_registry() -> &'static ReleaseHookRegistry { GLOBAL_REGISTRY.get_or_init(ReleaseHookRegistry::new) }
```

**Trait:** `crates/rez-next-release-hook/src/hook.rs:12-83` — `name()`, `new(source_path)`,
`pre_build(...)`, `pre_release(...)`, `post_release(...)`; all three events default to `Ok(())`.
Cancellation is signalled by `ReleaseHookError::Cancelled`
(`crates/rez-next-release-hook/src/lib.rs:53-55`).

**Events:** `crates/rez-next-release-hook/src/event.rs:11-49` — `PreBuild` / `PreRelease` /
`PostRelease` with `label()`, `noun()`, `func_name()`.

**Builtin hooks:** `crates/rez-next-release-hook/src/builtin.rs:307-325`
```rust
registry.register("noop",    |_path| Ok(Box::new(NoopHook) as Box<dyn ReleaseHook>));
registry.register("logging", |path| Ok(Box::new(LoggingHook::new(path)?) as Box<dyn ReleaseHook>));
registry.register("email",   |path| Ok(Box::new(EmailHook::new(path)?) as Box<dyn ReleaseHook>));
registry.register("webhook", |path| Ok(Box::new(WebHook::new(path)?) as Box<dyn ReleaseHook>));
```

### The `email` and `webhook` builtins are stubs

`crates/rez-next-release-hook/src/builtin.rs:170-174` (identical shape at `:153-157` and `:187-191`):
```rust
tracing::info!(
    "EmailHook: pre_release - would send email to {:?}",
    self.config.to_addresses
);
Ok(())
```
`crates/rez-next-release-hook/src/builtin.rs:244-248` (identical at `:262-266`, `:279-285`):
```rust
tracing::info!(
    "WebHook: pre_build - would send {} request to {}",
    self.config.method, self.config.url
);
Ok(())
```
No SMTP client, no HTTP client. Both hooks are pure logging. (`WebHook::new` does validate
that `url` is non-empty, `builtin.rs:226-230`.)

### Hooks are dead code in the release path

`grep -rn "rez-next-release-hook" --include=Cargo.toml rez-next/` → only
`crates/rez-next-python/Cargo.toml:37`. The only consumer is the **Python binding layer**
(`crates/rez-next-python/src/release_hook_bindings.rs:6`), which exposes
`get_release_hook_types()` / `create_release_hook()`. Neither
`crates/rez-next-build/src/release.rs` nor `src/cli/commands/release.rs` depends on the crate
or calls into it. The Python `run_hooks()` helper is defined but never called
(R0 evidence).

### rez spec side

**Abstract base:** `src/rez/release_hook.py:39-131` — `name()` classmethod (`:46-49`),
`__init__(source_path)` (`:51-60`), `pre_build` (`:62`), `pre_release` (`:86`),
`post_release` (`:112`).
**Event enum:** `src/rez/release_hook.py:134-143`.
**Factories:** `src/rez/release_hook.py:12-36` — `get_release_hook_types()`,
`create_release_hook(name, source_path)`, `create_release_hooks(names, source_path)`.
**Invocation:** `src/rez/build_process.py:369-387` (`run_hooks`) reads
`self.package.config.release_hooks` (default `[]`, `src/rez/rezconfig.py:800`) and dispatches
via `getattr(hook, hook_event.__name__)`, converting `ReleaseHookCancellingError` into
`ReleaseError` (`:379-383`) and swallowing other `RezError`s as debug output (`:384-387`).
**Shipped plugins:** `amqp`, `command`, `emailer` (see premise item 2).

### Registration contract, side by side

| | rez-next | upstream Rez |
| --- | --- | --- |
| Discovery | in-process `OnceLock` global registry; `register(name, factory)` (`registry.rs:34-40`, `builtin.rs:307-325`) | filesystem plugin family: any module under `rezplugins/release_hook/` (or an `extend_path` extension) exposing `register_plugin()` returning the class (`src/rezplugins/release_hook/amqp.py:102-103`, `command.py:209-210`, `emailer.py:155-156`; `__init__.py:5-6`) |
| Extensible by third parties without recompiling | **No** | Yes |
| Name | `ReleaseHook::name() -> String` (`hook.rs:14-16`) | `ReleaseHook.name() -> str` classmethod (`release_hook.py:46-49`) |
| Construction | `new(source_path: PathBuf)` (`hook.rs:19-21`) | `__init__(self, source_path)` (`release_hook.py:51-60`) |
| Config access | ad-hoc file read (`builtin.rs:197-208`, `:291-301`) | `self.type_settings`/`self.settings` from `package.config.plugins.release_hook` (`release_hook.py:59-60`) |
| Cancellation | `ReleaseHookError::Cancelled` (`lib.rs:53-55`) | `ReleaseHookCancellingError` (`src/rez/release_hook.py:80-83`) |

**判定:** **GAP (needs rez-next work)**, on three counts:
1. Hooks are never invoked by any release path.
2. `email` and `webhook` are non-functional stubs; upstream's `command` hook (the one that
   actually does work at most sites) has no equivalent.
3. The Rust registry is compile-time-only — there is no out-of-tree plugin contract.

**VX impact:** BLOCKING if VX needs any post-release action (notification, publication,
index refresh). Today the only way is to wrap the CLI and do it externally.

### Documentation defect found while verifying R2

`crates/rez-next-python/src/plugins_bindings.rs:206-209` advertises:
```rust
let release_hooks = [
    ("emailer", "Send email notification on release"),
    ("command", "Run custom command on release"),
];
```
Neither name is in the registry (`noop`, `logging`, `email`, `webhook` — `builtin.rs:310-324`).
`rez_next.plugins` therefore lists two release hooks that do not exist, and omits the four that do.
**判定:** GAP (documentation/API correctness). **VX impact:** NON-BLOCKING but misleading.

---

## R3. `release_vcs` plugin family

**rez-next ships three `ReleaseVCS` implementations**, all real:

| Type | File | Mechanism |
| --- | --- | --- |
| git | `crates/rez-next-build/src/vcs/git.rs` | `git2` crate, feature-gated `git`, **on by default** |
| hg | `crates/rez-next-build/src/vcs/hg.rs` | shells out to `hg` (`hg.rs:52-58`) |
| svn | `crates/rez-next-build/src/vcs/svn.rs` | shells out to `svn` (`svn.rs:30-31`) |

Feature default: `crates/rez-next-build/Cargo.toml:35-36`
```toml
[features]
git = ["dep:git2"]
default = ["git"]
```

Detection: `crates/rez-next-build/src/vcs/mod.rs:425-448`
```rust
pub fn detect_vcs(repo_path: &Path) -> Option<Box<dyn ReleaseVCS + Send + Sync>> {
    if repo_path.join(".git").exists() { ... }
    if repo_path.join(".hg").exists() { ... }
    if repo_path.join(".svn").exists() { ... }
    None
}
```

**Which does the CLI expose?** Only git. `src/cli/commands/release.rs:242-249`
```rust
fn ensure_supported_vcs(vcs_type: &str) -> RezCoreResult<()> {
    if vcs_type == "git" {
        return Ok(());
    }
    Err(RezCoreError::BuildError(format!(
        "Release VCS '{vcs_type}' is not supported; only git releases currently provide transactional tagging"
    )))
}
```
`--vcs` is accepted (`src/cli/commands/release.rs:24-26`) but any value other than `git` —
including `hg` and `svn`, whose implementations exist — is rejected at `:91`.
The CLI's own `detect_vcs` (`:230-240`) recognises `.git`, `.svn`, `.hg`, so an hg checkout
is detected and then refused.

**Python layer ships zero VCS implementations.** `crates/rez-next-python/python/rez_next/release_vcs.py:24-52`
defines an ABC with an auto-registering `__init_subclass__` (`:190-196`) and factories
`get_release_vcs_types()` (`:204-212`) and `create_release_vcs()` (`:215+`).
`grep -rn "ReleaseVCS)" --include=*.py crates/rez-next-python/python/` → **0 hits**; no
subclass exists. Therefore `_registry` is permanently empty, `get_release_vcs_types()`
returns `[]`, and `create_release_vcs()` always raises.

**rez spec side:** `src/rez/release_vcs.py:17-20` (`get_release_vcs_types()` via
`plugin_manager.get_plugins('release_vcs')`) and `:23-69` (`create_release_vcs(path, vcs_name)`
with nearest-root disambiguation and a multi-VCS error, `:60-66`).
Shipped implementations: `src/rezplugins/release_vcs/git.py`, `hg.py`, `svn.py`, `stub.py`
— plus `src/rezplugins/release_vcs/rezconfig.py`.
CLI exposure: `src/rez/cli/release.py:23-25` — `--vcs` with `choices=vcs_types`; all three
selectable.

**Precise statement of the gap:**

| Capability | rez-next | upstream |
| --- | --- | --- |
| git implementation | Yes | Yes |
| hg implementation | Yes (library) | Yes |
| svn implementation | Yes (library) | Yes |
| hg/svn selectable from `release` CLI | **No** — hard error | Yes (`--vcs hg`) |
| Python `create_release_vcs()` | **Broken** — empty registry | Returns a working instance |
| Nearest-VCS-root disambiguation (`src/rez/release_vcs.py:33-69`) | **No** — first match in fixed git→hg→svn order wins (`vcs/mod.rs:425-448`) | Yes, with `levels_up` and an explicit ambiguity error |
| `find_vcs_root` walking up parent directories | **No** — only the given directory is checked | Yes (`walk_up_dirs`, `src/rez/release_vcs.py:123-140`) |

**判定:**
- Shipped implementations (git/hg/svn): **ALIGNED**.
- CLI exposure: **INTENTIONAL DEVIATION (documented)** — `docs/production-readiness.md:37-38`
  states: *"CLI release currently supports Git. Mercurial and SVN are available through the
  lower-level VCS library but are not part of the CLI release contract."*
- Python `release_vcs` plugin family: **GAP**.
- Parent-directory VCS root discovery: **GAP** (a package nested inside a repo — the normal
  layout — is only detected if `.git`/`.hg`/`.svn` is in the package directory itself;
  `detect_vcs` joins the marker onto `repo_path` directly, `vcs/mod.rs:426/434/441`).

**VX impact:** hg/svn CLI restriction — NON-BLOCKING (documented, and VX uses git).
Python `create_release_vcs()` broken — BLOCKING for Python consumers.
No parent-directory discovery — BLOCKING for monorepo layouts.

---

## R4. Tag policy — naming, and refusing to move an existing tag

### Naming

| Path | Format | Evidence |
| --- | --- | --- |
| Rust `ReleaseManager` | `{name}-{version}` | `crates/rez-next-build/src/release.rs:668-678` |
| Rust CLI `release` | `{name}-{version}` | `src/cli/commands/release.rs:104`, `:169` |
| Python `BuildProcessHelper` | **`v{version}`** (overridable by config) | `crates/rez-next-python/python/rez_next/build_process.py:289-304` |

`crates/rez-next-build/src/release.rs:668-678`
```rust
fn release_tag_name(package: &Package) -> String {
    format!("{}-{}", package.name, package.version.as_ref().map(|v| v.as_str()).unwrap_or("unknown"))
}
```

`crates/rez-next-python/python/rez_next/build_process.py:295-304`
```python
tag_format = "v{version}"
from rez_next import config as cfg

try:
    cfg_tag = cfg.get("plugins.release_vcs.tag_name", None)
    if cfg_tag:
        tag_format = cfg_tag
except (AttributeError, KeyError):
    pass  # Config may not have the expected structure
return tag_format.format(version=version)
```

**rez spec side:** `src/rez/build_process.py:359-367`
```python
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
Default: `src/rezplugins/release_vcs/rezconfig.py:12` — `tag_name = "{qualified_name}"`
(≈ `name-version`), with the note at `:8-11` warning against a bare `{version}`.

**判定:**
- Rust tag name `{name}-{version}`: **ALIGNED** with the upstream default.
- Python tag name `v{version}`: **GAP** — diverges from both upstream's default and from
  rez-next's own Rust paths, and upstream explicitly warns against exactly this shape
  (version collisions when one repo hosts several packages).
- Configurable via `plugins.release_vcs.tag_name`: **ALIGNED** in the Python path; **absent**
  in both Rust paths (hardcoded format string).

### Refusing to move an existing tag

**Evidence (rez-next):** yes, and the reasoning is explicit.

`crates/rez-next-build/src/release.rs:606-617`
```rust
/// Returns `true` when the tag already existed *and* the policy let the
/// release continue anyway. Step 9 uses that to skip `create_tag`: the real
/// providers create tags with `force = false` and do not pre-check for
/// existence, so re-tagging an existing name would fail and turn an
/// installed release into a reported failure. Forcing the tag is not an
/// option — it would move an already-released version's tag onto a new
/// commit, which is exactly the provenance tampering this policy prevents.
```

Enforced in two places:
1. `check_existing_tag` — `crates/rez-next-build/src/release.rs:627-662`:
   `Some(false)` → hard error `"Release tag '{}' already exists. Use --ignore-existing-tag to override."`
   (`:643-646`); `Some(true)` / `None` → warn and set `tag_pre_existed = true` (`:632-654`).
2. Step 9 skips `create_tag` when the tag pre-existed — `crates/rez-next-build/src/release.rs:396-401`
   ```rust
   if let Some(ref vcs_impl) = vcs
       && result.errors.is_empty()
       && !tag_pre_existed
   {
       self.create_vcs_tag(vcs_impl.as_ref(), &package, message, &mut result)?;
   }
   ```

Also documented for SDK consumers at `docs/release-sdk.md:133-161`.

Separately, the CLI path refuses with an `Err` before building:
`src/cli/commands/release.rs:103-111`.

**rez spec side:** upstream leaves this to the VCS plugin. `create_release_tag`
(`src/rez/release_vcs.py:185-195`) has no "must not move" language, and the git plugin calls
`git tag` (annotation) through `self._cmd(...)`, which raises on non-zero exit
(`src/rez/release_vcs.py:222-227`) — so an existing tag fails the command, but by accident of
`git`'s behaviour rather than by contract. Upstream's *default* is to **not check at all**:
`src/rezplugins/release_vcs/rezconfig.py:21-42` — `check_tag = False`, "Generally this is not
needed, because Rez won't re-release over the top of an already-released package anyway".

**判定:** **INTENTIONAL DEVIATION (stricter than upstream, and deliberate).**
rez-next's "check before build, never move, never re-create" is a stronger and well-documented
guarantee than upstream's. It is a behavioural difference, not a defect.
**VX impact:** NON-BLOCKING — BLOCKING only for a workflow that depends on re-tagging a version
in place, which upstream also discourages.

---

## R5. `release_message`, `release_path` / `packages_path`

### `release_message`

**Evidence (rez-next):** accepted by the CLI and used **only** as the git tag annotation.

- Input: `-m/--message` (`src/cli/commands/release.rs:17-18`), `-F/--message-file`
  (`:21-22`, read at `:364-366`).
- Used: `src/cli/commands/release.rs:170-174`
  ```rust
  let message = args.message.clone()
      .or_else(|| read_message_file(args.message_file.as_ref()))
      .unwrap_or_else(|| format!("Release {}", tag));
  ```
  → `create_git_tag(&working_dir, &tag, &message, args.verbose)` (`:177`) →
  `git tag -a <tag> -m <message>` (`src/cli/commands/release.rs:322-326`).
- SDK: `message` param of `release_with_vcs`, defaulting to `Release {name}-{version}`
  (`crates/rez-next-build/src/release.rs:692-693`); in dry-run it is echoed as a warning
  (`:336-338`).

**Not persisted.** `write_release_metadata` (`crates/rez-next-build/src/release.rs:732-776`)
ignores its `package` argument entirely (`_package: &Package`, `:734`) and writes only
`vcs_metadata.json` (`:744`). `build_package` copies `package.py` verbatim
(`crates/rez-next-build/src/release.rs:590-597`). So the installed package carries **no**
`release_message`, `changelog`, `revision`, `previous_version`, or `timestamp`.

Note: the `Package` struct *does* have those fields —
`crates/rez-next-package/src/package/serialize.rs:41-45` serializes `timestamp`, `revision`,
`changelog`, `release_message` and `previous_version` — the release workflow just never
populates them.

**rez spec side:** upstream materialises release data as package attributes on the installed
package. `src/rez/build_process.py:414-448` (`get_release_data`) returns
`{vcs, revision, changelog, previous_version, previous_revision}`;
`src/rezplugins/build_process/local.py:444-446` adds `release_message`:
```python
release_data = self.get_release_data()
release_data["release_message"] = release_message
variant_ = variant.install(release_path, overrides=release_data)
```
Changelog is truncated per `max_package_changelog_chars` (`src/rez/build_process.py:440-442`).

**判定:** **GAP (needs rez-next work).**
**VX impact:** BLOCKING. `rez inspect <pkg> --release-message` / `--changelog` /
`--previous-version` equivalents cannot work, and any VX tooling that reads release provenance
off the installed package has nothing to read. `vcs_metadata.json` is a rez-next invention with
no upstream equivalent.

### `release_path` / `packages_path`

**Evidence (rez-next):**
- `release_packages_path` — `src/cli/commands/release.rs:369-371`
  ```rust
  fn get_release_path() -> String { RezCoreConfig::load().release_packages_path }
  ```
- Install-path resolution in the SDK — `crates/rez-next-build/src/release.rs:457-476`
  ```rust
  let install_base = match self.mode {
      ReleaseMode::Local | ReleaseMode::DryRun => PathBuf::from(expand_home(&config.local_packages_path)),
      ReleaseMode::Release => {
          let rp = &config.release_packages_path;
          if !rp.is_empty() && rp != "~/.rez/packages/int" {
              PathBuf::from(expand_home(rp))
          } else {
              PathBuf::from(expand_home(&config.local_packages_path))
          }
      }
  };
  ```
- Package search paths for `rez test` — `src/cli/commands/test.rs:165-177` (config `packages_path`,
  `--paths` override, `--no-local` exclusion).

**rez spec side:**
- `src/rez/rezconfig.py:73` — `release_packages_path = "~/.rez/packages/int"`.
- Pre-release existence check: `src/rez/build_process.py:305-307`
  ```python
  release_path = self.package.config.release_packages_path
  if not os.path.exists(release_path):
      raise ReleaseError("Release path does not exist: %r" % release_path)
  ```
- `rez test` path handling: `src/rez/cli/test.py:60-65`.

**判定:** **ALIGNED**, with one gap: rez-next does **not** check that the release path exists
before building (`src/cli/commands/release.rs:120-164` builds straight into
`PathBuf::from(get_release_path())`), whereas upstream fails fast
(`src/rez/build_process.py:305-307`). The SDK's `create_dir_all` will silently create it
(`crates/rez-next-build/src/release.rs:532-537`), so a typo in `release_packages_path`
produces a silently-wrong install location instead of an error.
**VX impact:** NON-BLOCKING (but a real footgun; a misconfigured release path is a silent
mis-publish, not a loud failure).

---

## R6. `--dry-run`, `--no-message`, per-variant release

### `--dry-run`

Two different implementations:

1. **CLI** — `src/cli/commands/release.rs:56-58` (flag), `:113-118` (behaviour):
   ```rust
   if args.dry_run {
       println!("[dry-run] Would release {}-{}", package.name, version_str);
       println!("[dry-run] VCS: {}", vcs_type);
       println!("[dry-run] Release repository: {}", get_release_path());
       return Ok(());
   }
   ```
   Runs **after** VCS detection, repo validation (`:98-100`) and the existing-tag check
   (`:103-111`), so it does surface those failures. Does not report what would be built.

2. **SDK** — `ReleaseMode::DryRun`, `crates/rez-next-build/src/release.rs:333-340`:
   ```rust
   if self.mode == ReleaseMode::DryRun {
       result.install_path = format!("[dry-run] {}", result.install_path);
       result.success = true;
       if let Some(msg) = message { result.warnings.push(format!("[dry-run] note: {}", msg)); }
       return Ok(result);
   }
   ```
   `docs/release-sdk.md:103-119` documents the resulting trap explicitly: a dry run sets
   `success = true` **unconditionally**, so it can return `success == true` together with a
   non-empty `errors` (e.g. `["VCS validation failed: Repository is not clean"]`).

**rez spec side:** upstream `rez release` has **no** `--dry-run` flag
(`src/rez/cli/release.py:15-42` — the parser adds `-m/--message`, `--vcs`, `--no-latest`,
`--ignore-existing-tag`, `--skip-repo-errors`, `--no-message`, plus the common build args).
The closest upstream analogue is the per-variant dry-run install at
`src/rezplugins/build_process/local.py:398-404`, which skips a variant whose destination
already exists.

**判定:** **INTENTIONAL DEVIATION (addition)** — rez-next is strictly more capable.
The `success = true` + non-empty `errors` combination is a genuine API hazard and is at least
documented. **VX impact:** NON-BLOCKING, provided callers check `errors` as the doc instructs.

### `--no-message`

**Evidence (rez-next):** **absent** from `ReleaseArgs` (`src/cli/commands/release.rs:15-63`).
`grep -n "no_message\|no-message" -r src/` → 0 hits. The Python config surface has
`prompt_release_message: bool = False` (`crates/rez-next-python/python/rez_next/config.py:741`,
schema at `:935`) but no Rust CLI reads it, and there is no `$EDITOR` prompt implementation.

**rez spec side:** `src/rez/cli/release.py:39-41`
```python
parser.add_argument(
    "--no-message",
    dest="no_message",
    action="store_true",
    help="do not prompt for release message.",
)
```
with the editor-prompt workflow at `src/rez/cli/release.py:86-139` (opens
`config.editor` on a `rez-release-message-<sha1>.txt` temp file, strips the changelog section
and header, and aborts on an empty message unless the user chooses Continue).

**判定:** **GAP (needs rez-next work)** — flag missing and no message-prompting workflow.
**VX impact:** NON-BLOCKING for CI (which passes `-m` explicitly); BLOCKING for a
human-driven release flow that relies on the editor prompt.

### Per-variant release

**Evidence (rez-next):** the CLI releases each variant. `src/cli/commands/release.rs:135`
```rust
for variant_index in release_variant_indices(&package, args.variants.as_deref())? {
```
with selection at `:184-227` (all variants by default, `--variants` accepts a comma-separated
index list, out-of-range indices are rejected at `:210-216`).
Per-variant the CLI resolves a build context (`:137-141`) and starts a build (`:142-155`).

The **SDK** path (`ReleaseManager`) handles variants much more weakly — `build_package`
(`crates/rez-next-build/src/release.rs:540-581`) only creates variant subdirectories and writes
`variant.json`; it never builds or installs variant payloads.

**rez spec side:** `src/rezplugins/build_process/local.py:112-119` —
`visit_variants(self._release_variant, variants=variants, ...)`, with index resolution
(`resolve_variant_indices`, `:213-220`) and per-variant build/test/install (`:394-447`).
Upstream `--variants` takes `nargs='+', type=int` and supports **negative indices**
(`src/rez/cli/build.py:74-77`), which `setup_parser_common` shares with `rez-release`.

**判定:** **ALIGNED** for the CLI. **GAP** for the SDK (`ReleaseManager` does not release
variant payloads). Minor gap: rez-next `--variants` rejects negative indices
(`src/cli/commands/release.rs:207-210`) where upstream accepts them.
**VX impact:** CLI per-variant release — NON-BLOCKING (ALIGNED).
SDK variant handling — BLOCKING for any VX tool driving `ReleaseManager` directly.

---

## R7. `ReleaseManager` + `release_with_vcs()` + `ReleaseMode`

**Evidence (rez-next):** `crates/rez-next-build/src/release.rs:27-38`
```rust
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum ReleaseMode {
    /// Normal release to `release_packages_path`.
    ///
    /// Falls back to `local_packages_path` when `release_packages_path` is
    /// empty or still the default `~/.rez/packages/int`.
    Release,
    /// Local release to `local_packages_path`
    Local,
    /// Dry run: validate but don't write
    DryRun,
}
```
String parsing: `crates/rez-next-build/src/release.rs:40-49` —
`"local"` → `Local`; `"dry-run"`/`"dry_run"` → `DryRun`; anything else → `Release`.
Constructor: `:142` — `new(mode: ReleaseMode, skip_build: bool, skip_tests: bool)`.
`release()` → `release_with_vcs(..., None)` at `:178-184`.
Python mirror: `crates/rez-next-python/src/release_bindings.rs:464-478, 529-580`.

**Mapping to upstream `rez release` CLI flags:**

| `ReleaseMode` | Upstream `rez release` equivalent | 判定 |
| --- | --- | --- |
| `Release` | Default behaviour — install to `release_packages_path` (`src/rez/cli/release.py:142`; `src/rez/build_process.py:305`) | ALIGNED (with the `~/.rez/packages/int` fallback being a rez-next addition) |
| `Local` | **No upstream `rez release` equivalent.** Nearest analogue is `rez build --install --prefix <path>` (`src/rez/cli/build.py:92-97`), which is `rez build`, not `rez release` | INTENTIONAL DEVIATION (rez-next addition) |
| `DryRun` | **No upstream equivalent** — `rez release` has no `--dry-run` (see R6) | INTENTIONAL DEVIATION (rez-next addition) |

**Upstream `rez release` flags with no `ReleaseMode` counterpart** (`src/rez/cli/release.py:15-42`):

| Upstream flag | rez-next support |
| --- | --- |
| `-m`, `--message` | Yes — `-m/--message` (`src/cli/commands/release.rs:17-18`) |
| `--vcs` | Parsed (`:24-26`) but non-`git` values are rejected at `:91`/`:242-249` |
| `--no-latest` | **Parsed and ignored** — `no_latest` appears only in the `ReleaseArgs` struct (`:45-46`); `grep -n "no_latest" src/cli/commands/release.rs` returns that definition and nothing else |
| `--ignore-existing-tag` | Yes — `:41-42`, enforced at `:103-111` and in `check_existing_tag` (`crates/rez-next-build/src/release.rs:628-655`) |
| `--skip-repo-errors` | Yes — `:37-38`, `:98-100` |
| `--no-message` | **Absent** (R6) |
| `--process` | Yes — `:32-34`, default `"local"` |
| `--buildsys` | Parsed (`:28-30`); not consumed by `execute` |
| `--variants` | Yes — `:48-50` (no negative indices) |
| `--dry-run` | rez-next addition |

**判定:** `Release` ALIGNED; `Local` and `DryRun` are INTENTIONAL DEVIATIONS (additions).
`--no-latest` being a declared-but-ignored flag is a **GAP** — `ensure_latest` semantics
(upstream `src/rez/build_process.py:340-347`) are not implemented, so rez-next will happily
release an older version over a newer published one. rez-next's Python path *does* implement
it (`build_process.py:263-271`), which widens the divergence between paths B and C.

**VX impact:** `--no-latest` silently ignored — BLOCKING. (`downstream consumers could receive
a version downgrade with no warning.`) `Local`/`DryRun` additions — NON-BLOCKING.

---

## R8. `ReleaseVCS` trait — 9 required + 4 default methods vs upstream

### rez-next side (`crates/rez-next-build/src/vcs/mod.rs:110-203`)

**9 required:**

| # | Method | Line | Notes |
| --- | --- | --- | --- |
| 1 | `get_type_name(&self) -> &str` | `:112` | |
| 2 | `get_repo_root(&self) -> Result<PathBuf>` | `:115` | |
| 3 | `is_clean(&self) -> Result<bool>` | `:118` | |
| 4 | `get_current_branch(&self) -> Result<String>` | `:121` | no upstream counterpart |
| 5 | `get_latest_commit(&self) -> Result<String>` | `:124` | |
| 6 | `tag_exists(&self, tag: &str) -> Result<bool>` | `:127` | |
| 7 | `create_tag(&self, tag: &str, message: &str) -> Result<()>` | `:130` | |
| 8 | `get_changelog(&self, from_rev: Option<&str>, to_rev: Option<&str>) -> Result<String>` | `:133-137` | |
| 9 | `get_metadata(&self) -> Result<VCSMetadata>` | `:140` | no upstream counterpart |

**4 with default implementations:**

| # | Method | Line | Default behaviour |
| --- | --- | --- | --- |
| 10 | `validate_repo_state(&self) -> Result<()>` | `:148-156` | `is_clean()` only; error text `"Repository is not clean"` |
| 11 | `is_releasable_branch(&self) -> Result<Option<bool>>` | `:163-166` | `Ok(None)` |
| 12 | `get_current_revision(&self) -> Result<VCSRevision>` | `:179-183` | wraps `get_latest_commit()` |
| 13 | `export(&self, _revision: &VCSRevision, _path: &Path) -> Result<()>` | `:198-202` | `Err("export() not implemented for this VCS")`; overridden in `git.rs:486`, `hg.rs`, `svn.rs:245` |

`docs/release-sdk.md:63-64` states the same split:
*"Nine methods are required. `validate_repo_state()`, `is_releasable_branch()`,
`get_current_revision()`, and `export()` have default implementations."*

### upstream side (`src/rez/release_vcs.py:72-232`)

| Upstream member | Line | Kind | rez-next counterpart |
| --- | --- | --- | --- |
| `name()` | `:91-94` | classmethod, abstract | `get_type_name()` (1) |
| `find_executable(name)` | `:96-102` | classmethod, concrete | **absent** |
| `is_valid_root(path)` | `:104-113` | classmethod, abstract | **absent** (folded into `detect_vcs`) |
| `search_parents_for_root()` | `:115-120` | classmethod, abstract | **absent** — rez-next never walks parents |
| `find_vcs_root(path)` | `:122-140` | classmethod, concrete; returns `(vcs_root, levels_up)` | `get_repo_root()` (2) — returns a bare `PathBuf`, no `levels_up` |
| `validate_repostate()` | `:142-144` | abstract | `validate_repo_state()` (10) — **defaulted, not abstract** |
| `get_current_revision()` | `:146-155` | abstract; "can be any type (str, dict etc.)" | `get_current_revision()` (12) — defaulted, typed `VCSRevision` |
| `get_changelog(previous_revision=None, max_revisions=None)` | `:157-172` | abstract | `get_changelog(from_rev, to_rev)` (8) — **different parameter semantics** |
| `tag_exists(tag_name)` | `:174-182` | abstract | `tag_exists()` (6) |
| `create_release_tag(tag_name, message=None)` | `:185-195` | abstract | `create_tag(tag, message)` (7) — `message` is non-optional |
| `export(revision, path)` | `:197-209` | classmethod, abstract | `export()` (13) — defaulted to `Err`, and an instance method, not a classmethod |
| `_cmd(*nargs)` | `:211-232` | concrete helper | **absent** (each impl rolls its own) |
| `is_clean()` | — | **absent upstream** | rez-next required method (3) |
| `get_current_branch()` | — | **absent upstream** | rez-next required method (4) |
| `get_latest_commit()` | — | **absent upstream** | rez-next required method (5) |
| `get_metadata()` | — | **absent upstream** | rez-next required method (9) |
| `is_releasable_branch()` | — | **absent upstream** | rez-next defaulted method (11) |

### Differences that have behavioural consequences

1. **`validate_repostate()` is abstract upstream, defaulted in rez-next, and the git
   implementation does not override it.**
   `crates/rez-next-build/src/vcs/mod.rs:148-156` only calls `is_clean()`.
   `grep -c "fn validate_repo_state" crates/rez-next-build/src/vcs/git.rs` → **0**, so a git
   release validates cleanliness and nothing else. (`hg.rs:299-318` and `svn.rs:306` do
   override it; `hg.rs` additionally rejects active mq patches, `:307-315`.)
   Upstream `GitReleaseVCS.validate_repostate()` (`src/rezplugins/release_vcs/git.py:93-141`)
   additionally checks: bare repository (`:94-96`), upstream/tracking branch with the
   `plugins.release_vcs.git.allow_no_upstream` setting (`:98-106`), the
   `releasable_branches` regex list (`:108-122`), uncommitted changes (`:124-130`), and
   ahead/behind vs the remote (`:132-141`).
   **判定: GAP (git-specific; hg and svn are closer to upstream).**

2. **`get_changelog` parameter semantics differ.**
   rez-next: `get_changelog(from_rev, to_rev)` — a range.
   upstream: `get_changelog(previous_revision=None, max_revisions=None)` — since a revision,
   capped. Upstream's contract (`src/rez/release_vcs.py:157-172`) also requires a meaningful
   changelog when `previous_revision` is not an ancestor.
   Call site: `crates/rez-next-build/src/release.rs:718` — `vcs.get_changelog(None, None)`,
   and the Python path calls `self._vcs.get_changelog(max_revisions=...)` (`build_process.py:339`),
   which does not match the Rust trait signature.
   **判定: GAP.**

3. **`export()` is a classmethod upstream, an instance method in rez-next**, and the default
   (`crates/rez-next-build/src/vcs/mod.rs:198-202`) returns `Err`.
   `git.rs:486`, `hg.rs` and `svn.rs:245` all override it, so coverage is complete in practice —
   but the signature and the classmethod/instance-method split differ from upstream.
   **判定: INTENTIONAL DEVIATION** (upstream `src/rez/release_vcs.py:197-209` makes it a
   classmethod; upstream also treats it as essential: *"You must ensure that a revision contains
   enough information to clone/export/checkout the repo elsewhere - otherwise you will not be
   able to implement `export`"*, `:150-154`).

4. **`is_releasable_branch()` is never consulted.**
   `grep -rn "is_releasable_branch" --include=*.rs rez-next/` — the only non-definition hits
   are delegation shims (`crates/rez-next-build/src/vcs/mod.rs:365`, `:420`) and tests
   (`crates/rez-next-build/src/vcs/mod.rs:792-913`,
   `crates/rez-next-python/src/release_bindings_tests.rs:648-650`).
   `GitVCS` hardcodes the policy (`crates/rez-next-build/src/vcs/git.rs:571-578`):
   ```rust
   Ok(Some(branch == "main" || branch == "master" || branch.starts_with("release/")))
   ```
   Upstream makes this configurable via `releasable_branches`
   (`src/rezplugins/release_vcs/rezconfig.py:14-19`) and enforces it in
   `validate_repostate()`. Since nothing calls it, the hardcoded policy has no effect.
   **判定: GAP.**

5. **No nearest-root disambiguation.** covered in R3.

6. **Error typing differs.** rez-next collapses all VCS failures into `RezCoreError::BuildError`
   (e.g. `crates/rez-next-build/src/vcs/mod.rs:151-154`); upstream has a dedicated
   `ReleaseVCSError` (`src/rez/exceptions.py`), which matters because `repo_operation()`
   selectively suppresses only `ReleaseVCSError` when `skip_repo_errors` is set
   (`src/rez/build_process.py:202-208`). rez-next's `skip_repo_errors`
   (`src/cli/commands/release.rs:37-38`, `:98-100`) disables validation wholesale instead of
   downgrading it to a warning, so a genuinely broken repo silently skips *all* checks.
   **判定: GAP.**

**判定 (overall):** The trait is a reasonable Rust-idiomatic adaptation, and the 9-required /
4-default split is accurately documented. It is **not** a drop-in mapping of upstream's
contract: one abstract upstream method has no counterpart at all (`is_valid_root`,
`search_parents_for_root`, `find_executable`), two are renamed with different signatures
(`find_vcs_root`→`get_repo_root` losing `levels_up`; `get_changelog` range vs since/max),
one is demoted from abstract to defaulted (`validate_repostate`), and four rez-next methods
have no upstream basis (`is_clean`, `get_current_branch`, `get_latest_commit`, `get_metadata`,
`is_releasable_branch`).

**VX impact:** BLOCKING for anyone porting an upstream `ReleaseVCS` subclass or writing a
custom rez-next VCS whose repo validation must match upstream's git checks. NON-BLOCKING for
the plain git release path.

---

# Summary

| # | Item | 判定 | VX impact |
| --- | --- | --- | --- |
| T1 | `rez test` CLI exists; flag surface | ALIGNED (2 cosmetic deviations) | NON-BLOCKING |
| T2a | per-package `package_test.py` / `rez:test` | INTENTIONAL DEVIATION (not a Rez feature) | BLOCKING if VX depends on it |
| T2b | `tests` attribute found and run (Python API) | GAP | BLOCKING |
| T2c | `rez:setup` / `rez:teardown` | N/A — not a Rez feature | NON-BLOCKING |
| T2d | pytest / unittest detection | ALIGNED (neither side has it) | NON-BLOCKING |
| T3 | `--extra-packages` | ALIGNED | NON-BLOCKING |
| T4 | `tests` dict / list entries | **GAP** | **BLOCKING** (parse failure ⇒ package invisible) |
| T5 | post-install tests vs upstream pre-install + rollback | **GAP** | **BLOCKING** |
| T6 | Test result model / exit codes | ALIGNED (+1 extra status) | NON-BLOCKING |
| R0 | three divergent release implementations | **GAP** | **BLOCKING** |
| R1 | phase order | ALIGNED (tag-check-first, tag-last) | NON-BLOCKING |
| R1 | rollback on build/test failure | **GAP** | **BLOCKING** |
| R1 | release-path test discovery (`tests()` as callable) | **GAP** — silently runs nothing | **BLOCKING** |
| R2 | release_hook system never invoked | **GAP** | **BLOCKING** |
| R2 | `email` / `webhook` builtins are stubs; no `command` hook | **GAP** | **BLOCKING** |
| R2 | no out-of-tree hook registration | **GAP** | BLOCKING |
| R2 | `plugins` listing advertises nonexistent hooks | GAP (docs/API) | NON-BLOCKING |
| R3 | git/hg/svn implementations exist | ALIGNED | NON-BLOCKING |
| R3 | CLI rejects hg/svn | INTENTIONAL DEVIATION (documented) | NON-BLOCKING |
| R3 | Python `create_release_vcs()` — empty registry | **GAP** | **BLOCKING** |
| R3 | no parent-directory VCS root discovery | **GAP** | **BLOCKING** (monorepos) |
| R4 | tag name `{name}-{version}` (Rust) | ALIGNED | NON-BLOCKING |
| R4 | tag name `v{version}` (Python) | **GAP** | BLOCKING |
| R4 | refuses to move an existing tag | INTENTIONAL DEVIATION (stricter) | NON-BLOCKING |
| R5 | `release_message` not persisted to package | **GAP** | **BLOCKING** |
| R5 | `release_packages_path` / `packages_path` | ALIGNED | NON-BLOCKING |
| R5 | no release-path existence precheck | GAP | NON-BLOCKING (footgun) |
| R6 | `--dry-run` | INTENTIONAL DEVIATION (addition) | NON-BLOCKING |
| R6 | `--no-message` / editor prompt | **GAP** | NON-BLOCKING (CI) / BLOCKING (human flow) |
| R6 | per-variant release (CLI) | ALIGNED | NON-BLOCKING |
| R6 | per-variant release (SDK) | **GAP** | **BLOCKING** |
| R7 | `ReleaseMode::Release` | ALIGNED | NON-BLOCKING |
| R7 | `ReleaseMode::Local` / `DryRun` | INTENTIONAL DEVIATION (additions) | NON-BLOCKING |
| R7 | `--no-latest` declared but ignored | **GAP** | **BLOCKING** |
| R8 | `ReleaseVCS` trait — 9 required / 4 default | documented accurately; not a drop-in mapping | BLOCKING for custom VCS / ports |
| R8 | git `validate_repo_state` checks cleanliness only | **GAP** (hg/svn OK) | **BLOCKING** (git is the only CLI-supported VCS) |

---

# Candidate GitHub issues

Each entry below is a proposed issue for `vx-org/rez-next`. Bodies are public-safe: no
internal issue keys, no internal hostnames, no local paths beyond repo-relative ones.

---

### 1. `tests` in package.py: support dict and list test definitions

Rez's `tests` attribute accepts three shapes per `src/rez/package_test.py`: a command string,
a list of argv, or a dict with `command`, `requires`, `run_on` and `on_variants` keys.

rez-next models the attribute as `HashMap<String, String>` and rejects anything else at parse
time, so a package using the dict or list form fails to load at all — not just during testing,
but for `build`, `release` and every resolve that touches it.

Observed:

- `crates/rez-next-package/src/package/types.rs:44` — `pub tests: HashMap<String, String>,`
- `crates/rez-next-package/src/python_ast_parser/extract.rs:150-153` returns
  `PackageParse("Unsupported test definition for '{key}': only string commands are supported")`
  for any non-string value.
- `src/cli/commands/test.rs:239-243` and
  `crates/rez-next-package/src/package/test_runner.rs:209-213` hardcode
  `requires: vec![]`, `run_on: vec!["default"]`, `on_variants: None`, so the per-test fields
  exist in `TestDefinition` but can never be populated.

Expected: parse all three shapes, thread `requires` into the test-environment resolve, honour
`run_on` tags for selection (upstream defaults to the `default` tag when no test is named), and
implement `on_variants` (including the `{"type": "requires", "value": [...]}` filter form).

---

### 2. Package tests run after install with no rollback on failure

Rez runs package tests *before* the package definition is published and rolls back on failure.
rez-next runs them after, and leaves the installed payload in place.

Upstream, `src/rezplugins/build_process/local.py`:
- `:428-441` runs `_run_tests(run_on=["pre_release"], ...)` then, on `PackageTestError`,
  calls `self._rmtree(build_result["variant_install_path"])` and `cancel_variant_install()`.
- `:449-461` documents the ordering: payload installed, tests run against a temp variant whose
  root is redirected at the real payload, real `package.py` updated only on success.

rez-next, `crates/rez-next-build/src/process.rs`:
- `:39-56` and `:288-296` place `PackageTesting` **after** `Installing`.
- `:612-623` returns `(false, ...)` on the first failing test with no cleanup.

Consequence: a failing test leaves the payload visible to consumers, and there is no `run_on`
filter, so there is no way to express "run these before publishing".

Expected: move package tests ahead of the definition publish, and on failure remove the
installed payload and notify the package repository so the release is fully cancelled.

---

### 3. `ReleaseManager` release path never runs package tests

`ReleaseManager::release_with_vcs` step 5 calls `run_tests`, which discovers tests by importing
`tests` from `package.py` and **calling it as a function**, expecting a JSON array of strings
(`crates/rez-next-build/src/release.rs:869-884`).

In Rez `tests` is a dict attribute, not a callable. Because the loader can only produce
`HashMap<String, String>`, `tests()` raises `TypeError`, which the `except Exception` handler
swallows into `"[]"`. The release then emits
`"No test commands found in package.py::tests()"` (`:826-828`), which reads as "package has no
tests" rather than "discovery is broken".

Two further problems in the same function: tests execute with `current_dir(install_path)`
(`:920-935`) and no resolved environment, and per-test `requires` / `run_on` / extra packages
are unavailable.

Expected: read the parsed `tests` attribute the same way `rez test` does
(`src/cli/commands/test.rs:233-246`), run each command in a resolved environment, and surface
a discovery error instead of an empty test list.

---

### 4. Release hooks are never invoked

rez-next ships a release-hook system (`crates/rez-next-release-hook`) with a registry, a
`ReleaseHook` trait, a `ReleaseHookEvent` enum and four builtins
(`crates/rez-next-release-hook/src/builtin.rs:307-325`: `noop`, `logging`, `email`, `webhook`),
plus a Python `run_hooks` helper
(`crates/rez-next-python/python/rez_next/build_process.py:306-317`).

None of it is reachable from a release:

- `grep -rn "rez-next-release-hook" --include=Cargo.toml` matches only
  `crates/rez-next-python/Cargo.toml:37`. Neither `crates/rez-next-build/src/release.rs` nor
  `src/cli/commands/release.rs` depends on the crate.
- `run_hooks` is referenced only inside its own definition; `BuildProcessHelper.release`
  (`build_process.py:382-396`) calls `pre_release()`, `build()` and `post_release()` only.
- `run_hooks` imports `run_hooks` from `rez_next.release_hook`, which does not export one; the
  `except (ModuleNotFoundError, ImportError)` branch logs at debug level and returns, so the
  failure is silent.

Upstream invokes hooks at `src/rezplugins/build_process/local.py:103-109` (pre-release) and
`:122-128` (post-release), reading names from `package.config.release_hooks`
(`src/rez/rezconfig.py:800`) and dispatching via `getattr(hook, hook_event.__name__)`
(`src/rez/build_process.py:369-387`).

Expected: call pre-release hooks after validation and before the variant loop, and post-release
hooks after the variants are released but before tagging; convert a cancelling error into a
release failure and log non-cancelling hook errors without aborting.

---

### 5. Release hook builtins `email` and `webhook` are non-functional stubs

`EmailHook` and `WebHook` log what they would do and return `Ok(())`. There is no SMTP or HTTP
client in the crate.

- `crates/rez-next-release-hook/src/builtin.rs:153-157`, `:170-174`, `:187-191` —
  `tracing::info!("EmailHook: ... would send email to {:?}", self.config.to_addresses)`
- `crates/rez-next-release-hook/src/builtin.rs:244-248`, `:262-266`, `:279-285` —
  `tracing::info!("WebHook: ... would send {} request to {}", self.config.method, self.config.url)`

Upstream ships `emailer` (real SMTP send, `src/rezplugins/release_hook/emailer.py`),
`command` (executes `pre_build_commands` / `pre_release_commands` / `post_release_commands`,
with `cancel_on_error` and `stop_on_error`, `src/rezplugins/release_hook/command.py`) and
`amqp`. rez-next has no equivalent of `command`, which is the hook most sites actually rely on.

Expected: either implement the hooks or mark them clearly as non-functional so callers do not
configure a notification path that silently does nothing. Adding a `command` hook would cover
the largest gap.

---

### 6. `rez_next.plugins` advertises release hooks that do not exist

`crates/rez-next-python/src/plugins_bindings.rs:206-209` registers:

```rust
let release_hooks = [
    ("emailer", "Send email notification on release"),
    ("command", "Run custom command on release"),
];
```

The registry contains `noop`, `logging`, `email`, `webhook`
(`crates/rez-next-release-hook/src/builtin.rs:310-324`). Neither advertised name resolves, and
neither registered name is listed.

Expected: derive the advertised list from `get_release_hook_types()` instead of a hardcoded
array, so the two cannot drift.

---

### 7. Python `release_vcs` has no registered implementations

`crates/rez-next-python/python/rez_next/release_vcs.py` defines an abstract `ReleaseVCS` with
an auto-registering `__init_subclass__` (`:190-196`) and factories
`get_release_vcs_types()` (`:204-212`) and `create_release_vcs()` (`:215`).

No subclass ships with the package — `grep -rn "ReleaseVCS)" --include=*.py` under the Python
package returns nothing — so `_registry` stays empty, `get_release_vcs_types()` returns `[]`
and `create_release_vcs()` always raises.

Upstream ships `src/rezplugins/release_vcs/{git,hg,svn}.py`, all discoverable through the
plugin family.

Expected: either bind the existing Rust `GitVCS` / `MercurialVCS` / `SvnVCS` implementations
into the Python registry, or ship Python implementations behind the same names.

---

### 8. VCS detection does not search parent directories

`detect_vcs` (`crates/rez-next-build/src/vcs/mod.rs:425-448`) checks only the directory it is
given, joining the marker onto `repo_path` directly:

```rust
if repo_path.join(".git").exists() { ... }
if repo_path.join(".hg").exists() { ... }
if repo_path.join(".svn").exists() { ... }
```

Upstream walks up (`src/rez/release_vcs.py:123-140`, using `search_parents_for_root()` and
`walk_up_dirs`) and disambiguates by proximity, returning `(vcs_root, levels_up)` and raising
when two VCS roots are equally close (`src/rez/release_vcs.py:33-69`).

A package nested inside a repository — the normal layout — is therefore only detected when the
VCS marker sits in the package directory itself.

Expected: walk up to the nearest ancestor containing a supported marker, and report an explicit
error when markers from different systems are found at the same depth.

---

### 9. Git repository validation checks cleanliness only

`GitVCS` does not override `validate_repo_state` — `grep -c "fn validate_repo_state"` in
`crates/rez-next-build/src/vcs/git.rs` returns 0 — so the trait default applies
(`crates/rez-next-build/src/vcs/mod.rs:148-156`): `is_clean()` and nothing else.
(`hg.rs:299-318` and `svn.rs:306` do override it, so only git is affected — which matters
because git is the only VCS the CLI release path accepts.)

Upstream `GitReleaseVCS.validate_repostate()` (`src/rezplugins/release_vcs/git.py:93-141`) also
checks for a bare repository, for an upstream/tracking branch (gated on
`plugins.release_vcs.git.allow_no_upstream`), for the `releasable_branches` regex list, for
uncommitted changes, and for being ahead of or behind the remote.

Relatedly, `is_releasable_branch()` (`crates/rez-next-build/src/vcs/git.rs:571-578`) hardcodes
`main` / `master` / `release/*` and is never called from anywhere in the release flow — the only
call sites are delegation shims and tests. Upstream makes the same policy configurable via
`plugins.release_vcs.releasable_branches` and enforces it inside `validate_repostate()`.

Expected: implement the missing checks in `GitVCS::validate_repo_state`, and either wire
`is_releasable_branch` into validation with a configurable branch list or remove it.

---

### 10. `--no-latest` is accepted and ignored

`ReleaseArgs` declares `--no-latest` (`src/cli/commands/release.rs:45-46`), but the flag is
never read — it appears nowhere else in the file. `ensure_latest` is therefore always
effectively on, with one difference: upstream *enforces* it
(`src/rez/build_process.py:340-347` raises when a newer published version exists), while
rez-next implements neither the check nor the flag.

Upstream also exposes the check through `create_build_process(..., ensure_latest=...)`
(`src/rez/cli/release.py:77`).

The Python path does implement it (`crates/rez-next-python/python/rez_next/build_process.py:263-271`),
so the CLI and the Python API disagree.

Expected: implement the check in the CLI release path and honour `--no-latest`, or remove the
flag so it does not imply a guarantee that does not exist.

---

### 11. Release omits `release_message`, `changelog`, `revision` and `previous_version` from the installed package

`write_release_metadata` (`crates/rez-next-build/src/release.rs:732-776`) takes `package` as an
unused parameter (`_package: &Package`, `:734`) and writes only `vcs_metadata.json` (`:744`).
`build_package` copies `package.py` verbatim (`:590-597`). The installed package therefore
carries no release provenance.

The `Package` struct already has the fields — `crates/rez-next-package/src/package/serialize.rs:41-45`
serializes `timestamp`, `revision`, `changelog`, `release_message` and `previous_version` — the
release workflow just never populates them. `release_message` is used solely as the git tag annotation
(`src/cli/commands/release.rs:170-177`).

Upstream builds the equivalent data in `get_release_data` (`src/rez/build_process.py:414-448`),
adds `release_message` (`src/rezplugins/build_process/local.py:444-446`), and installs the
variant with those overrides, so the attributes are readable off the released package.

Expected: write the release data into the installed package definition, truncating the
changelog per a configurable character limit as upstream does.

---

### 12. Three release implementations disagree on tag format, push behaviour and whether a build runs

rez-next has three release paths that do not share an implementation:

| Path | Entry point | Real build | Tag format | Push |
| --- | --- | --- | --- | --- |
| `ReleaseManager::release_with_vcs` | Rust SDK | no (dirs + copy `package.py` only) | `{name}-{version}` | no |
| `commands::release::execute` | `rez-next release` | yes, per variant | `{name}-{version}` | yes (`git push origin <tag>`) |
| `BuildProcessHelper.release` | `rez_next.build_process` | yes | `v{version}` | no |

`grep -rn "ReleaseManager\|release_with_vcs\|ReleaseMode" --include=*.rs src/` returns nothing,
confirming the CLI does not sit on top of the SDK.

Two consequences worth calling out:

- The Python tag format `v{version}` (`crates/rez-next-python/python/rez_next/build_process.py:295`)
  disagrees with both Rust paths and with upstream's default `tag_name = "{qualified_name}"`
  (`src/rezplugins/release_vcs/rezconfig.py:12`). Upstream explicitly warns against a bare
  `{version}` tag at `:8-11`, because versions collide when one repository hosts several
  packages.
- `ReleaseManager::build_package` (`crates/rez-next-build/src/release.rs:516-600`) creates
  directories and copies `package.py` but never invokes a build system, so a release driven
  through the SDK installs a definition with no payload.

Expected: pick one implementation to own the workflow, have the CLI and Python paths delegate
to it, and express tag format through a single configurable setting.

---

### 13. `ReleaseVCS` trait does not cover upstream's repository-contract methods

The trait (`crates/rez-next-build/src/vcs/mod.rs:110-203`) is a reasonable Rust adaptation, but
it is not a drop-in mapping of `src/rez/release_vcs.py:72-232`, which makes porting an existing
VCS implementation harder than it needs to be.

Concrete divergences:

- `is_valid_root(path)`, `search_parents_for_root()` and `find_executable(name)`
  (upstream `:104-120`) have no counterpart.
- `find_vcs_root(path)` returns `(vcs_root, levels_up)` (upstream `:122-140`); rez-next's
  `get_repo_root()` returns a bare `PathBuf`, dropping the proximity information that upstream
  uses for disambiguation.
- `validate_repostate()` is abstract upstream (`:142-144`) but defaulted in rez-next
  (`:148-156`), where it only calls `is_clean()`.
- `get_changelog(previous_revision, max_revisions)` (upstream `:157-172`) is a "since revision,
  capped" contract; rez-next's `get_changelog(from_rev, to_rev)` (`:133-137`) is a range. The
  Python path calls it as `get_changelog(max_revisions=...)` (`build_process.py:339`), matching
  neither signature.
- `export()` is a classmethod upstream (`:197-209`) and an instance method in rez-next
  (`:198-202`), where it defaults to `Err`. git, hg and svn all override it, so behaviour is
  covered; the signature split is what makes porting awkward.
- `is_clean`, `get_current_branch`, `get_latest_commit`, `get_metadata` and
  `is_releasable_branch` have no upstream basis.

Also relevant: rez-next collapses all VCS failures into `RezCoreError::BuildError`, while
upstream has a dedicated `ReleaseVCSError`. Upstream's `repo_operation()`
(`src/rez/build_process.py:202-208`) suppresses only that type when `skip_repo_errors` is set,
downgrading repo problems to warnings. rez-next's `--skip-repo-errors`
(`src/cli/commands/release.rs:98-100`) disables validation wholesale.

Expected: introduce a VCS-specific error type, add the missing root-discovery hooks, and align
`get_changelog` with upstream's signature — or document each divergence deliberately in
`docs/release-sdk.md`.

---

### 14. Release does not verify that the release path exists

Upstream fails fast when the configured release path is missing
(`src/rez/build_process.py:305-307`):

```python
release_path = self.package.config.release_packages_path
if not os.path.exists(release_path):
    raise ReleaseError("Release path does not exist: %r" % release_path)
```

rez-next builds straight into `PathBuf::from(get_release_path())`
(`src/cli/commands/release.rs:120-164`), and `build_package` calls `create_dir_all` on the
install path (`crates/rez-next-build/src/release.rs:532-537`). A typo or a stale setting in
`release_packages_path` therefore creates a new directory tree and reports success, instead of
erroring.

Expected: validate the release path during pre-release and abort when it does not exist,
matching upstream.

---

### 15. `rez-next test`: missing upstream extras (per-test argv passthrough and `{root}` expansion)

Two smaller gaps in the otherwise-aligned `rez test` implementation:

- **Extra argv passthrough.** Upstream forwards arguments after `--` to a single named test
  (`src/rez/cli/test.py:67-73`, applied at `src/rez/package_test.py:420-424`), erroring when
  more than one test is named. rez-next has no equivalent.
- **`{root}` expansion.** Upstream expands command strings through the variant
  (`src/rez/package_test.py:412-418`, `command = variant.format(command)`). rez-next's
  `execute_test_command` passes the raw string to the shell
  (`src/cli/commands/test.rs:480-488`), so a test command written as
  `"python -m unittest -s {root}/tests"` is executed literally. The build pipeline does expand a
  fixed set of tokens (`crates/rez-next-build/src/process.rs:604-608` — `{root}`, `{base}`,
  `{this.root}`, `{this.base}`), so the two paths disagree on the same command string.

Expected: add argv passthrough, and share one token-expansion routine between `rez test` and
the build pipeline's package-test step.

---

### 16. Python `PackageTestRunner` ignores its package argument and runs without a resolved environment

`rez_next.package_test.PackageTestRunner` is documented as the drop-in for
`rez.package_test.PackageTestRunner`
(`crates/rez-next-python/python/rez_next/package_test.py:1-10`), but its behaviour does not
match.

`crates/rez-next-package/src/package/test_runner.rs`:
- `:114-131` — `new(package_spec)` resolves the working directory from
  `std::env::current_dir()`; `load_test_definitions` (`:162-188`) takes `_package_spec`
  (unused) and searches only that directory. The package being tested is never looked up.
  Compare `src/rez/package_test.py:130-137`, which resolves the request through the package
  search path and raises `PackageNotFoundError` on failure.
- `:183-186` — when nothing is found the function returns `Ok` with empty definitions, so the
  caller sees "no tests" rather than "package not found".
- `:396-401` — test commands are executed with `Command::new(program).args(...)` and no
  environment, so the test does not run inside a rez context. The CLI path does set one
  (`src/cli/commands/test.rs:512-514`).

Expected: route the Python runner through the same package lookup and environment resolution as
the CLI (`src/cli/commands/test.rs`), and raise when the requested package cannot be found.
