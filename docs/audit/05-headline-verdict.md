# Headline item: `install_variant` / variant lookup by URI

Verified first-hand against rez-next `main` (0.3.10) and upstream Rez `3.4.0`.

## Verdict: **GAP (needs rez-next work) — NOT an intentional deviation**

Both directions fail *closed* (explicit error, not a silent miss), which is the
right behaviour for an unimplemented operation. Neither is documented as a
permanent design choice — `docs/production-readiness.md:26-40` lists them under
**"Explicit exclusions"** with the word *"yet"*:

> - Variant lookup by URI and direct filesystem `install_variant` are not yet
>   supported.  (`docs/production-readiness.md:33-34`)

"Not yet" is a temporary state, so this is a gap, not a deliberate deviation.

### Evidence — rez-next side

| Item | Location | Behaviour |
|---|---|---|
| `install_variant()` | `crates/rez-next-repository/src/package_repository/filesystem.rs:538-548` | Returns `Err(RezCoreError::Repository("Filesystem variant installation is not implemented; use the build or release workflow"))` |
| Contract | `crates/rez-next-repository/src/package_repository/mod.rs:129` | Trait method declared; `:207` routes `dry_run` through the same call |
| Test | `crates/rez-next-repository/src/package_repository/filesystem.rs:967-980` | `install_variant_fails_closed_until_supported` asserts `is_err()` — the name states the intent |
| `get_variant_from_uri()` | `crates/rez-next-python/src/package_uri_functions.rs:181-190` | Raises `PyNotImplementedError("variant URI lookup is not implemented; iterate variants from a resolved package instead")` |
| `get_variant()` | `crates/rez-next-python/src/package_uri_functions.rs:197-207` | Same `NotImplementedError` |
| Python surface | `crates/rez-next-python/python/rez_next/package_repository.py:254`, `:265` | `install_variant` / dry-run wrapper declared |

### Evidence — rez spec side

| Item | Location |
|---|---|
| `PackageRepository.install_variant()` contract | `src/rez/package_repository.py:335-338` |
| Filesystem implementation | `src/rezplugins/package_repository/filesystem.py:901-961` |
| `PackageRepository.get_variant_from_uri()` contract | `src/rez/package_repository.py:218` |
| Filesystem implementation | `src/rezplugins/package_repository/filesystem.py:632-666` |

### What `install_variant` actually means upstream — a correction

It is **not** "adopt a prebuilt directory tree as a variant". It installs a
`VariantResource` **sourced from another package repository** into this one
(`src/rez/package_repository.py:335-338`, *"Use this function to install a variant
from some other package repository into this one"*). There is no
`rez/utils/install_variant.py`, no `rez-install-variant` console entry point, and
`rez build` has no no-build / files-only mode — `--prefix` only redirects the
destination repository (`src/rez/cli/build.py:96-98`).

The repository is explicitly not responsible for payloads
(`src/rez/package_repository.py:71-75`): *"even though a package repository does
determine where package payloads should go, it is not responsible for creating or
copying these payloads."*

### What "variant lookup by URI" actually means upstream — a correction

The syntax is **`<package-uri>[<variant-index>]`** with an *integer* index, plus
`pkg[]` for the null variant of a variant-less package — produced at
`src/rez/package_resources.py:488-491` and parsed at
`src/rezplugins/package_repository/filesystem.py:640-660`.

It is **not** a request syntax. `rez env` rejects `pkg[1]`, `pkg[platform-linux]`
and friends with `PackageRequestError` / `VersionError` — the package-name regex
(`src/rez/utils/formatting.py:26-28`) and the requirement separator set
(`src/rez/version/_requirement.py:139`) both exclude `[`. The URI form is consumed
by `rez cp --uri` (`src/rez/cli/cp.py:79,92-99`), `rez pkg-cache`
(`src/rez/cli/pkg-cache.py:19,75`) and `rez context --show-uris`
(`src/rez/cli/context.py:53,146,180`).

A variant *subpath* such as `platform-linux/arch-x86_64` is computed, never
selected by request.

## What IS aligned: the variant install layout

The gap is **installation and URI lookup**, not variant layout. rez-next mirrors
Rez's subpath algorithm exactly:

- rez-next `crates/rez-next-package/src/install_layout.rs:53-87` — non-hashed
  variants push each canonical requirement as a path component; hashed variants
  push `sha1("['a', 'b']")` where the string is the Python list repr.
- Upstream `src/rez/package_resources.py:493-520` —
  `sha1(str(list(map(str, variant_requires))))` for hashed variants,
  `os.path.join(*[x.safe_str() for x in variant_requires])` otherwise.
- rez-next cites the upstream source at `install_layout.rs:19`.
- Upstream builds and installs variants strictly **one at a time** — own build
  path, own install path, own freshly resolved context, own `variant.install()`
  call (`rezplugins/build_process/local.py:157-166`, `:229-240`, `:390`; driver
  loop `src/rez/build_process.py:210-239`).

Judgement: **ALIGNED** for `platform-<p>/arch-<a>/` layout and for
`hashed_variants`. One deliberate omission: rez-next does not implement Rez's
optional variant *shortlinks* (`config.use_variant_shortlinks`,
`variant_shortlinks_dirname`), documented at `install_layout.rs:17` as
"Optional repository shortlinks are not canonical installation paths."
That is an **intentional deviation** with no impact on package correctness —
shortlinks are a symlink convenience layer, not part of a package's identity.

## Is it blocking the VX migration?

**No.** The error message itself names the route that works:
*"use the build or release workflow"*. VX's multi-platform packages are produced
by **building** (`rez build --install`), which installs the variant directly and
never calls `install_variant()`. The layout that produces is identical to what
VX publishes today — `witr/0.3.4/platform-<p>/arch-<a>/payload/...` — because
`install_layout.rs` reproduces Rez's subpath.

`install_variant()` is only needed to copy an **already-built** variant from one
repository into another, i.e. what `rez cp` does. VX's publish path tarballs a
build output tree, so it does not need that operation either.

Two caveats worth recording:

- `docs/production-readiness.md:39-40` also excludes **advanced copy options**
  (variant selection, destination renaming, timestamp preservation, dry-run).
  This matters for determinism — see
  [`06-determinism-spec-gap.md`](06-determinism-spec-gap.md).
- Both gaps are now tracked upstream: [#332](https://github.com/vx-org/rez-next/issues/332)
  (`install_variant`) and [#333](https://github.com/vx-org/rez-next/issues/333)
  (variant URI lookup).

**Conclusion:** `install_variant` / variant-URI lookup is a tracked
**non-blocking** gap. It blocks neither `rez build`-based construction nor
VX's publish layout. It blocks only a future "copy a variant between
repositories" workflow.
