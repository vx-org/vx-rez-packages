# Rez spec alignment audit — rez-next and the VX packaging protocol

Audit-only. No implementation code was changed in either repository.

## Baseline

| Side | Revision | Role |
| --- | --- | --- |
| **Specification** — `AcademySoftwareFoundation/rez` | `f622b81`, `_rez_version = "3.4.0"` (`src/rez/utils/_version.py:7`) | the Rez spec; every "rez spec side" citation resolves to this tree |
| **Implementation** — `vx-org/rez-next` | `97eef03`, `version = "0.3.10"` (`Cargo.toml`) | the implementation VX ships against |
| **Consumer** — `vx-org/vx-rez-packages` | `0c493bb` | the private protocol under examination |

The audit brief's own starting point was `docs/production-readiness.md`. This audit read it,
then verified every claim against source rather than repeating it.

## Reports

| # | Document | Scope |
| --- | --- | --- |
| 00 | [`00-rez-spec-baseline.md`](00-rez-spec-baseline.md) | the normative Rez reference this audit measures against (A–F, with a quick-lookup index) |
| 01 | [`01-build.md`](01-build.md) | build systems, `build_command`, `REZ_BUILD_*`, variants, requires, `rez build` CLI, build process, timestamp |
| 02 | [`02-test-release.md`](02-test-release.md) | `rez test`, `tests` attribute, release phases, release hooks, release VCS, tag policy, `ReleaseMode` |
| 03 | [`03-repo-ecosystem.md`](03-repo-ecosystem.md) | package repositories, copy/move/remove, caching, and the wider CLI surface |
| 04 | [`04-vx-protocol.md`](04-vx-protocol.md) | `recipe.json` + `tools/build_bundle.py` mapped onto the Rez spec, field by field |
| 05 | [`05-headline-verdict.md`](05-headline-verdict.md) | the headline item: `install_variant` / variant lookup by URI |
| 06 | [`06-determinism-spec-gap.md`](06-determinism-spec-gap.md) | the determinism / provenance gap, stated as a spec-layer question |

---

## Corrections to the audit brief

Six items in the brief do not survive contact with upstream Rez 3.4.0. They are listed first
because several of them change the verdict, not just the wording.

1. **`build.py` is not a Rez specification convention.** Upstream `custom` runs a
   `build_command` string (`src/rezplugins/build_system/custom.py:145-158`); there is no
   script-file mechanism. `build_system = "build.py"` is a rez-next extension.
   `build_command` also **takes precedence over** `build_system` when upstream selects a plugin —
   a package that declares `build_command` is routed to `custom` automatically
   (`src/rez/build_system.py:62-65`), so the minimal upstream form is just `build_command`.
   rez-next does neither: the token must be the literal `"build_command"`, or the extension
   form `build_system = "build.py"`. *This is the finding with the largest consequence for VX* —
   see "Verdict" below.
2. **Upstream's `build_system` family is `cmake`, `custom`, `make`** — three plugins
   (`src/rezplugins/build_system/`). rez-next's eight are a **superset**, so "rez-next is missing
   build systems" is not a gap. `scons`, `python` and `bez` are not in 3.4.0.
3. **`install_variant` does not mean "install a prebuilt directory tree".** It installs a
   `VariantResource` sourced from *another repository* into this one
   (`src/rez/package_repository.py:335-338`); the repository is explicitly not responsible for
   payloads (`:71-75`). There is no `rez-install-variant` entry point and `rez build` has no
   no-build mode.
4. **Variant URI is `<package-uri>[<index>]` with an integer index** — produced at
   `src/rez/package_resources.py:488-491`, parsed at
   `src/rezplugins/package_repository/filesystem.py:640-660`. It is **not** a request syntax:
   `rez env` rejects `pkg[1]` and `pkg[platform-linux]`. A variant *subpath* is computed, never
   selected by request.
5. **`--keep-tmp` is not a `rez build` flag, and `pre_build_requires` does not exist.** The only
   `--keep-tmpdirs` in upstream is on `rez selftest` (`src/rez/cli/selftest.py:44`). Upstream has
   `pre_build_commands`, never `pre_build_requires` (zero occurrences). Also,
   `variant_requires` is **not** a `package.py` attribute — it is a computed property returning
   `parent.variants[index]` (`src/rez/packages.py:407-417`).
   Four more upstream absences worth knowing before designing against them:
   `post_build_commands` does not exist (only `pre_build_commands`); `BuildStep` is not an
   upstream concept; `--process=remote` is registered but non-functional
   (`src/rezplugins/build_process/remote.py:21`); and `rez release` has no `--dry-run`, so
   rez-next's `--dry-run` is an addition rather than a parity item.
6. **Smaller scope corrections.** Upstream `release_hook` ships exactly `amqp`, `command`,
   `emailer` (no `github_repository` or `slack`). `package_filter` and `package_order` are core
   modules (`src/rez/package_filter.py`, `src/rez/package_order.py`), not plugin families in
   3.4.0. There is no `s3.py` in core Rez — S3 is a third-party plugin, so its absence from
   rez-next is not a spec gap.

---

## Verdict: can the VX migration start now?

**Yes for package construction. No for the published artifact — and that half is a
specification-layer question, not an implementation defect.**

### Construction: go

The package-side protocol is *already* Rez's. The checked-in `package.py` is valid Rez
(`name`, `version`, `description`, `tools`, a six-entry `variants` list, `commands()`), and the
published layout is Rez's layout:

```text
witr/0.3.4/platform-windows/arch-x86_64/payload/bin/witr.exe
       └─ <name>/<version>/  └─ non-hashed variant subpath ─┘
```

rez-next computes that subpath by mirroring Rez's `VariantResourceHelper._subpath`
(`crates/rez-next-package/src/install_layout.rs:53-87` vs
`src/rez/package_resources.py:493-520`), including the hashed-variant SHA-1 form. **Layout is not
a gap.** Download → verify SHA-256 → strip prefix → map into `payload/` under the variant root is
expressible as ordinary `build.py` strategy under the Rez `build_system` protocol.

### The one blocking item

**[rez-next#330](https://github.com/vx-org/rez-next/issues/330)** — the spelling of the
build-system selector. VX's goal is packages whose `package.py` is valid *upstream Rez*, and
upstream's spelling is `build_system = "custom"` + `build_command`. On rez-next today that
combination resolves to copy-only: the command never runs and the build reports success
(`crates/rez-next-build/src/lib.rs:99-101`, `systems/custom.rs:140-142`). The only working
spelling is the rez-next-specific token `build_command`, or the extension
`build_system = "build.py"`.

So the two goals — "spec-aligned `package.py`" and "builds on rez-next today" — are mutually
exclusive until #330 is fixed. Everything else in the construction path is compensable in a
wrapper or in `build.py`:

| Gap | Compensated how today |
| --- | --- |
| [#336](https://github.com/vx-org/rez-next/issues/336) child env has no `PATH` | wrapper restores `PATH` before invoking `rez build` |
| [#322](https://github.com/vx-org/rez-next/issues/322) plain build never copies `package.py` | wrapper copies it byte-for-byte |
| [#358](https://github.com/vx-org/rez-next/issues/358) script invoked twice (`build`, then `install`) | make `build.py` branch on `argv` |
| [#320](https://github.com/vx-org/rez-next/issues/320), [#351](https://github.com/vx-org/rez-next/issues/351) `binary_archive` cannot handle `tar.zst` / `7z` / bare binaries | do the extraction inside `build.py` |
| [#323](https://github.com/vx-org/rez-next/issues/323) `"custom"` silently degrades to copy-only | never write that literal |
| [#321](https://github.com/vx-org/rez-next/issues/321) / [#324](https://github.com/vx-org/rez-next/issues/324) target env vars unset, arch vocabulary | wrapper sets them from the resolved target |

### Release artifacts: specification-layer gap

Deterministic `.tar.zst`, `sha256sums.txt`, `manifest.json` and `provenance.json` have **no home
in the Rez specification**. Rez has no integrity primitive (every `hashlib` use is internal
SHA-1/MD5 for caching), no reproducibility primitive (no `SOURCE_DATE_EPOCH`, no
mtime/uid/gid/mode normalisation, no canonical archive), and no per-file manifest in the
repository contract. `timestamp` exists and is overridable
(`src/rezplugins/package_repository/filesystem.py:1433-1435`), but on the build and release path
it is unconditionally `int(time.time())` — and the one lever that could pin it,
`install_variant(overrides=...)`, is the operation rez-next does not implement.

Full reasoning in [`06-determinism-spec-gap.md`](06-determinism-spec-gap.md). Per the brief,
**no VX-side private fallback is proposed.** The question for product is whether these artifacts
remain a VX *publication-layer* contract — defensible, since they describe the release channel
rather than the package — or are folded into package payload metadata.

### The headline item, answered

**`install_variant` / variant-URI lookup = GAP (needs rez-next work), not an intentional
deviation, and NOT blocking.** Both fail closed with explanatory errors, and
`docs/production-readiness.md:33-34` calls them "not **yet** supported". Neither blocks
`rez build`-based construction or VX's publish layout; they only block copying an already-built
variant between repositories. Full evidence in
[`05-headline-verdict.md`](05-headline-verdict.md).

---

## Gap register → upstream issues

42 issues were filed on `vx-org/rez-next`. Six pre-dated this audit (filed from the earlier
`rez build` spike): #319–#324.

### Build

| Issue | Title |
| --- | --- |
| [#330](https://github.com/vx-org/rez-next/issues/330) | `build_system = "custom"` does not run `build_command`; only the non-Rez token does |
| [#331](https://github.com/vx-org/rez-next/issues/331) | `build_command` variable expansion hardcodes `{install}` and `{variant_index}` |
| [#355](https://github.com/vx-org/rez-next/issues/355) | `rez build` flags accepted but ignored (`--build-system`, `--process`, `--cba`, `--fail-graph`, `--scripts`, `--clean`, `--force`) |
| [#356](https://github.com/vx-org/rez-next/issues/356) | `pre_build_commands` is parsed but never executed |
| [#357](https://github.com/vx-org/rez-next/issues/357) | `REZ_BUILD_TYPE` hardcoded `local`; `REZ_BUILD_PACKAGE_*` are not upstream names |
| [#358](https://github.com/vx-org/rez-next/issues/358) | Custom scripts invoked twice per variant, with a different argument contract |
| [#359](https://github.com/vx-org/rez-next/issues/359) | Successful `build_command` is followed by an unconditional copy of the source tree |
| [#360](https://github.com/vx-org/rez-next/issues/360) | `build_requires` / `private_build_requires` not distinguished, leak into the installed package |
| [#351](https://github.com/vx-org/rez-next/issues/351) | `binary_archive` supports only zip and tar.gz |
| [#353](https://github.com/vx-org/rez-next/issues/353) | `binary_archive` download has no timeout, size cap, redirect policy or scheme check |
| [#352](https://github.com/vx-org/rez-next/issues/352) | Unknown `package.py` attributes parsed into `extra_fields`, then silently discarded |
| [#354](https://github.com/vx-org/rez-next/issues/354) | `Package.timestamp` never set by build or release |
| [#336](https://github.com/vx-org/rez-next/issues/336) | Custom build scripts do not run in a resolved context; `PATH` absent, cwd is the temp build cache |

### Test

| Issue | Title |
| --- | --- |
| [#337](https://github.com/vx-org/rez-next/issues/337) | `tests` rejects dict and list definitions; the package fails to load |
| [#338](https://github.com/vx-org/rez-next/issues/338) | Package tests run after install, with no rollback on failure |
| [#339](https://github.com/vx-org/rez-next/issues/339) | `ReleaseManager` never runs package tests, reports "no tests" instead of the failure |
| [#343](https://github.com/vx-org/rez-next/issues/343) | Python `PackageTestRunner` ignores its package argument, runs without a resolved environment |
| [#349](https://github.com/vx-org/rez-next/issues/349) | `rez test`: no per-test argv passthrough, and `{root}` is not expanded |

### Release

| Issue | Title |
| --- | --- |
| [#334](https://github.com/vx-org/rez-next/issues/334) | `release_hook` family does not match Rez's (`command` missing, `emailer` renamed) |
| [#340](https://github.com/vx-org/rez-next/issues/340) | Release hooks are never invoked from any release path |
| [#341](https://github.com/vx-org/rez-next/issues/341) | `email` / `webhook` are stubs; the advertised hook list does not match the registry |
| [#335](https://github.com/vx-org/rez-next/issues/335) | `rez release --vcs` accepts only git; hg and svn exist in the library |
| [#342](https://github.com/vx-org/rez-next/issues/342) | Python `release_vcs` registry is empty; `create_release_vcs()` always raises |
| [#344](https://github.com/vx-org/rez-next/issues/344) | VCS detection does not search parent directories |
| [#345](https://github.com/vx-org/rez-next/issues/345) | Git validation checks cleanliness only; branch policy hardcoded and unenforced |
| [#346](https://github.com/vx-org/rez-next/issues/346) | Three release implementations disagree on tag format, push, and whether a build runs |
| [#347](https://github.com/vx-org/rez-next/issues/347) | Release omits `release_message`, `changelog`, `revision`, `previous_version` |
| [#348](https://github.com/vx-org/rez-next/issues/348) | `--no-latest` accepted and ignored; release path never validated |
| [#350](https://github.com/vx-org/rez-next/issues/350) | `ReleaseVCS` trait diverges from upstream in ways that block porting |

### Repository, distribution and ecosystem

| Issue | Title |
| --- | --- |
| [#332](https://github.com/vx-org/rez-next/issues/332) | Implement `install_variant()` on the filesystem package repository |
| [#333](https://github.com/vx-org/rez-next/issues/333) | Implement variant URI lookup (`get_variant_from_uri`, `get_variant`) |
| [#361](https://github.com/vx-org/rez-next/issues/361) | `rez cp` / `rez mv` bypass the install path and lack `--keep-timestamp` |
| [#362](https://github.com/vx-org/rez-next/issues/362) | Two divergent filesystem repositories; the upstream-faithful one is Python-only |
| [#363](https://github.com/vx-org/rez-next/issues/363) | `packages_path` does not support `type@location` repository specs |
| [#364](https://github.com/vx-org/rez-next/issues/364) | Five of nine upstream shells missing; dispatch duplicated across two enums |
| [#365](https://github.com/vx-org/rez-next/issues/365) | `rez plugins` infers plugins by substring-matching package names |
| [#366](https://github.com/vx-org/rez-next/issues/366) | `rez depends` / `rez status` always return empty (`find_packages("")` is an exact lookup) |
| [#367](https://github.com/vx-org/rez-next/issues/367) | `yaml2py` absent; a `package.yaml` package is buildable but invisible to resolution |
| [#368](https://github.com/vx-org/rez-next/issues/368) | Three config systems; ~120 upstream settings inert in the Rust binary |
| [#369](https://github.com/vx-org/rez-next/issues/369) | `memcached_*` settings declared but never read |
| [#370](https://github.com/vx-org/rez-next/issues/370) | `rez bind` binder table and detector disagree; undetectable tools bind as 1.0.0 |
| [#371](https://github.com/vx-org/rez-next/issues/371) | Seven upstream top-level commands have no counterpart |

### Pre-existing (filed from the earlier `rez build` spike)

#319 Python build API inert · #320 `binary_archive` lacks zstd · #321 `REZ_BUILD_TARGET_*`
unset · #322 plain build never copies `package.py` · #323 `"custom"` degrades to copy-only ·
#324 host arch `amd64` vs `arch-x86_64`.

---

## Recommendation

1. **Standardise on the portable spelling** — `build_system = "custom"` +
   `build_command = "python {root}/build.py {install}"` — and drive [#330](
   https://github.com/vx-org/rez-next/issues/330) to closure, so VX packages stay valid upstream
   Rez rather than becoming rez-next-only.
2. **Do not build on `binary_archive`.** It is a rez-next extension (not Rez spec), driven
   entirely by environment variables, and covers 2 of the 5 payload formats VX needs
   ([#351](https://github.com/vx-org/rez-next/issues/351)). Put the fetch/verify/extract strategy
   in `build.py`.
3. **Drop the `installation-plan` dependency.** It is a rez-next-only command with no upstream
   counterpart; upstream computes the same fact locally in `_subpath`.
4. **Escalate the publication-layer question** (deterministic archive, checksums, provenance) to
   product. It is a Rez specification gap, and the brief forbids a VX-side private protocol as the
   answer.
5. **Pilot can start now** on a `zip` / bare-binary package, compensating the six items in the
   table above. The `tar.zst` packages wait on
   [#320](https://github.com/vx-org/rez-next/issues/320) or on in-`build.py` extraction.
