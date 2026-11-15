# Rez 3.4.0 — Authoritative Upstream Specification Baseline

Normative reference of what upstream Rez *specifies*, used to compare a re-specification
(e.g. `rez-next`) against it dimension by dimension.

For readability the baseline is kept as this index plus a set of chapters under
[`rez-spec-baseline/`](rez-spec-baseline/00-overview.md). The normative text is preserved
verbatim across those chapters: no section was added, removed or reworded. Part letters
(A–F), section numbers (1–27) and every `src/...:LINE` citation are unchanged, so `§A.1`
style references still resolve to the same content.

**Source of truth.** A read-only clone of upstream Rez (`AcademySoftwareFoundation/rez`,
branch `main`) at commit `f622b81`, version confirmed at `src/rez/utils/_version.py`
(`_rez_version = "3.4.0"`). See [Overview](rez-spec-baseline/00-overview.md) for the full
source-of-truth, citation-discipline and reading-convention notes.

## Chapters

| Chapter | Scope |
| --- | --- |
| [Overview, conventions & extension-point summary](rez-spec-baseline/00-overview.md) | purpose, source of truth, citation discipline, reading conventions, seven plugin types |
| [A. Build](rez-spec-baseline/a-build.md) | `build_system`, `build_command`, build-time env vars, variants, requires, `rez build` CLI, build process, remote build, timestamp (§§1–9) |
| [B. Test](rez-spec-baseline/b-test.md) | `rez test`, `package_test.py`, post-install tests (§§10–12) |
| [C. Release](rez-spec-baseline/c-release.md) | `rez release`, release phases, `release_vcs`, tag policy, `release_hook`, release metadata (§§13–18) |
| [D. Repository & distribution](rez-spec-baseline/d-repository-distribution.md) | `package_repository`, filters/order, copy/move/remove, caching (§§19–22) |
| [E. Ecosystem surface](rez-spec-baseline/e-ecosystem-surface.md) | individual capability statements, full top-level command list (§§23–24) |
| [F. Prebuilt-binary packages](rez-spec-baseline/f-prebuilt-binary-packages.md) | prebuilt-binary install mechanism, artifact provenance, reproducible builds (§§25–27) |
| [Quick-lookup index](rez-spec-baseline/quick-lookup-index.md) | flat `concept → src/...:LINE` citation list |
