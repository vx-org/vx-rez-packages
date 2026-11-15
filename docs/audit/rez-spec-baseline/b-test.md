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
    test_entry = {"command": test_entry}
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
    block=True,
)

if retcode:
    print_warning("Test command exited with code %d", retcode)
    self._add_test_result(test_name, variant, "failed", "Test failed with exit code %d" % retcode)
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
tests_schema = Schema(
    {
        Optional(str): Or(
            Or(str, [str]),
            extensible_schema_dict(
                {
                    "command": Or(str, [str]),
                    Optional("requires"): [Or(PackageRequest, And(str, Use(PackageRequest)))],
                    Optional("run_on"): Or(str, [str]),
                    Optional("on_variants"): Or(
                        bool,
                        {
                            "type": "requires",
                            "value": [Or(PackageRequest, And(str, Use(PackageRequest)))],
                        },
                    ),
                }
            ),
        )
    }
)
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
    print("")
    raise PackageTestError(
        "%d tests failed; the installation has been cancelled" % runner.num_failed
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

