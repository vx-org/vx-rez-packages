# Stage-1 pilot findings — zip and bare-binary samples

Scope: two minimal reproducible samples (bare binary, zip archive) mapping VX
private protocol to rez-native expression, plus the conflicts. No implementation,
no upstream changes.

Baselines: upstream rez `master` (`3.4.0`), rez-next `74da028` (0.3.10).

## Headline: rez-next#330 as filed is not reproducible

The stage-0 audit recorded **#330 — `build_system = "custom"` + `build_command`
silently no-ops** as the single blocking item, and the dispatch note for this
pilot said to stop and record a conflict if the samples hit it.

**The samples did not hit it, because the behaviour is not present at HEAD.**

In rez-next, `build_command` is checked **before** `build_system`:

```rust
// crates/rez-next-build/src/systems/mod.rs:157-168
if let Some(ref build_command) = package.build_command {
    if build_command == "false" || build_command.is_empty() {
        return Ok(BuildSystem::Custom(CustomBuildSystem::new("copy-only".to_string())));
    } else {
        return Ok(BuildSystem::Custom(CustomBuildSystem::new("build_command".to_string())));
    }
}
// only then is build_system consulted
```

and `Custom("build_command")` dispatches to a real executor:

```rust
// crates/rez-next-build/src/systems/custom.rs:140-148
"build_command" => self.execute_build_command(request, environment).await,
```

`execute_build_command` (same file, `:188`) reads the command, expands the
variables, and runs it through `ShellExecutor`. I confirmed by execution that
both spellings — `build_command` alone and `build_system = "custom"` +
`build_command` — reach that code path and invoke the command; the observed
failures were downstream (below), not a no-op.

This matches upstream rez, which also prefers `build_command` over
`build_system` (`src/rez/build_system.py:62-63`). **rez-next is aligned with the
spec here.**

`git log -L` dates the `build_command`-first branch to `fa4cbd3` (2026-04-05),
well before the stage-0 audit — so this is not a fix that landed after the audit,
either the issue was mis-filed or it described a since-changed code shape.

**Action**: #330 should be re-verified and closed or corrected, not treated as
the migration blocker. It is tracked-only per this pilot's scope; I have not
edited the upstream issue.

## Real blocker found: rez-next#336 (sub-process environment)

Both samples failed at the `Installing` step with an empty error. Root cause:
the sub-process environment is cleared and `PATH` is not restored, so the
interpreter in `build_command` cannot be found.

- `crates/rez-next-context/src/shell.rs:236-238` — `if !self.inherit_parent_env { cmd.env_clear(); }`
- `crates/rez-next-context/src/shell.rs:180` — `inherit_parent_env: false` by default
- `crates/rez-next-build/src/systems/custom.rs:203-205` — the executor is built
  with `.with_environment(...)` but **never** `.with_inherit_parent_env(true)`

Re-injecting `PATH` through `BuildConfig::build_env_vars` made the command run,
which isolates the defect to environment inheritance. This is a real,
reproducible blocker for any `build_command` that shells out — and it is exactly
the class of failure #330 described, which is likely how the two got conflated.

## Second real issue: unquoted path expansion on Windows

With `PATH` restored, the command still failed:

```text
can't open file 'C:\Users\...\Temp\.tmpXXXX\UsershallongAppDataLocalTemp.tmpXXXX\build.py'
```

`{root}` expands correctly (`custom.rs:253`), but the expanded Windows path is
handed to the detected shell **unquoted**. On this machine `ShellType::detect()`
resolves to Git Bash (`SHELL` is set), where unquoted backslashes are consumed as
escape characters, collapsing the path. Quoting `"{root}"` resolves it.

Under upstream rez the path is normalised through the shell
(`custom.py:144-152`, `sh.normalize_path`), so this is a rez-next-side portability
defect rather than a spec divergence.

## Confirmed aligned

- **Variant layout**: `rez-next-runtime installation-plan` on the `witr` fixture
  returns `variant_relative_path = "witr/0.3.4/platform-windows/arch-x86_64"` —
  byte-identical to upstream rez's non-hashed subpath
  (`os.path.join(*variant_requires)`, `src/rez/package_resources.py:493-522`).
  **Precondition: `hashed_variants` must stay false**, per the 2026-10-11 ruling.
- **Build-strategy stripping**: `build_system` / `build_command` / `preprocess` /
  `pre_build_commands` are removed at install time
  (`src/rez/package_resources.py:42-48`), so VX policy never enters the published
  package.
- **`REZ_BUILD_*` surface**: rez-next sets the same core variables
  (`crates/rez-next-build/src/environment.rs:69-121`) as upstream
  (`src/rez/build_system.py:263-295`). Divergences: rez-next hardcodes
  `REZ_BUILD_VARIANT_INDEX` to `"0"` and leaves `VARIANT_REQUIRES` /
  `VARIANT_SUBPATH` empty (`:119-121`), whereas upstream supplies real values;
  upstream has no `REZ_BUILD_PACKAGE_NAME` / `PACKAGE_VERSION` (rez-next adds
  them alongside the `PROJECT_*` pair).

## Spec-layer gaps (unchanged, escalated — no VX fallback proposed)

1. **`sha256` has no home in the rez package spec.** `grep -rn "sha256" src/rez/`
   → zero hits outside vendored code. Enforceable in `build.py`, never
   *declarable* by a package.
2. **No reproducibility model.** No `SOURCE_DATE_EPOCH` (only in
   `src/rez/vendor/distlib/scripts.py:270`), no mtime/uid/gid normalisation, no
   canonical archive format. `timestamp` is `int(time.time())` at release —
   metadata, not a reproducibility primitive.
3. **`rez build --install` regenerates `package.py`** via `dump_package_data`
   (`src/rezplugins/package_repository/filesystem.py:1445-1451`), losing
   comments, formatting and non-`*_commands` functions — opposite to VX's
   byte-exact copy rule.
4. **`tests` cannot assert output or bound runtime.** Schema allows only
   `command` / `requires` / `run_on` / `on_variants`
   (`src/rez/package_resources.py:101-121`). VX `smoke_test.expect` and
   `.timeout_seconds` have no rez equivalent.

## Reproduction

Both sample `package.py` files were validated against the rez-next runtime:

```bash
rez-next-runtime installation-plan \
    --definition docs/pilot/sample-a-binary/package.py \
    --platform windows --arch x86_64 --json
# sample_bin  -> sample_bin/1.0.0/platform-windows/arch-x86_64

rez-next-runtime installation-plan \
    --definition docs/pilot/sample-b-zip/package.py \
    --platform windows --arch x86_64 --json
# sample_zip  -> sample_zip/1.0.0/platform-windows/arch-x86_64
```

Sample B's second variant resolves to index 1
(`platform-linux/arch-x86_64`); an undeclared target such as `arm_64` fails
closed with a solver error rather than silently mis-resolving.

## Conclusion

Both samples are expressible in rez-native form. Construction-side policy —
fetch, sha256 verification, prefix stripping, N mappings, executable bits —
moves cleanly into `build.py`, which is precisely what `build_command` exists
for, and is stripped before publication. The unmappable items are the four
spec-layer gaps above, all publish-layer or test-semantics concerns, none of
which block building a rez-valid package.

**Can migration start? Yes** — and the previously-recorded blocker (#330) is not
actually blocking. The real gate is #336 (environment inheritance), which breaks
every `build_command` that shells out and should be prioritised ahead of #330.
Per the ruling, determinism artifacts stay as a publish-layer contract beside the
package, never folded into the payload.
