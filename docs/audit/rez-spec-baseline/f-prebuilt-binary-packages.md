# F. Prebuilt-binary packages

## 25. A standard "download a prebuilt binary and install it" mechanism

**There is no dedicated prebuilt-binary mechanism in Rez 3.4.0.** What exists is:

1. **The `custom` build system + `build_command` attribute** (§A.1.5) — a package may declare an
   arbitrary command, and that command may do anything, including fetch and unpack a tarball. Rez
   neither helps nor verifies.
2. **Upstream's own framing agrees:** the block of schema that declares `build_system` and
   `build_command` is literally commented as pre-built-package attributes:

```python
# src/rez/package_maker.py:86-89
# attributes specific to pre-built packages
Optional("build_system"):           str,
Optional("build_command"):          Or([str], str, False),
Optional("preprocess"):             _function_schema,
```

3. **The in-tree example is exactly a prebuilt-payload install**, with no build step at all —
   `example_packages/hello_world/package.py:24`:

```python
build_command = "python {root}/build.py {install}"
```

   and `example_packages/hello_world/build.py` copies already-built `bin/` and `python/` trees into
   the install path (`:34-49`), reading the paths from the Rez build env vars at `:52-58`:

```python
# example_packages/hello_world/build.py:52-58
if __name__ == "__main__":
    build(
        source_path=os.environ["REZ_BUILD_SOURCE_PATH"],
        build_path=os.environ["REZ_BUILD_PATH"],
        install_path=os.environ["REZ_BUILD_INSTALL_PATH"],
        targets=sys.argv[1:],
    )
```

   Note the `targets` idiom: the script keys off the `{install}` placeholder (`"install" in (targets
   or [])`, `:48-49`), which is the documented `build_command` expansion
   (`src/rezplugins/build_system/custom.py:157`).

4. **`rez bind`** is the other prebuilt-facing path — it packages software *already on the system*
   (§E.23) — and **`rez pip`** is the third, for python distributions (§E.23). Neither downloads
   arbitrary binaries via a Rez-specified mechanism.

**No download facility exists in Rez's build or install path.**
`ABSENT — searched: grep -rn "urlretrieve\|urlopen\|requests\.\|urllib\|def download\|wget\|curl "
src/rez/ src/rezplugins/ --include=*.py`, filtered to exclude `src/rez/vendor/`. The only surviving
hits are unrelated:

* `src/rez/utils/amqp.py:11`, `:165` — `urllib.parse.urlsplit`, used to parse an AMQP broker URL for
  the `amqp` release hook. Not a download.
* `src/rez/utils/memcached.py:72` — the string "requests" in a docstring about server health.
* Identifier collisions in `src/rez/solver.py` and `src/rez/rex.py` on the substrings `requests` /
  `requested` (e.g. `src/rez/solver.py:1308`, `src/rez/resolved_context.py:165`), i.e. *package
  requests*, not HTTP requests.

**No checksum / hash verification facility exists in Rez's build or install path.**
`ABSENT — searched: grep -rn "sha256\|md5\|checksum\|verify_checksum\|hashlib" src/rez/
src/rezplugins/ --include=*.py`, excluding `src/rez/vendor/`. Every hit is a *hash for identity,
layout or cache-keying* — none is an integrity check:

| Hit | Purpose |
|---|---|
| `src/rez/cli/release.py:87` | `sha1` of the working dir, to name the temp release-message file (`:89-91`). |
| `src/rez/package_cache.py:11` | `sha1` for the package-cache directory layout (`:1041`, `:1000`). |
| `src/rez/package_filter.py:12`, `:83-91` | `sha1` of `str(self)` — a filter identity, used as a resolve-cache key (`src/rez/resolver.py:115`). |
| `src/rez/package_order.py:8` | `sha1` orderer identity, likewise a resolve-cache key (`src/rez/resolver.py:107`). |
| `src/rez/package_resources.py:23`, `:497-500` | `sha1` for **hashed variant subpaths** — a path-layout device (§A.4.2), explicitly documented as such at `docs/source/variants.rst:69-90`. |
| `src/rez/resolver.py:17` | `sha1` for memoization keys. |
| `src/rez/utils/memcached.py:15`, `:189` | `md5` for memcached key hashing (`md5(key.encode("utf-8")).hexdigest()`). |
| `src/rez/utils/sourcecode.py:313`, `:334` | `sha1` of an `@include` module's source. |
| `src/rezplugins/build_process/local.py:26`, `:325` | `sha1` of an `@include` module's source. |

**The one hash that is written to disk is not a verification.** During install, Rez writes a
`<module>.sha1` sidecar next to each `@include` module
(`src/rezplugins/build_process/local.py:325-332`). It *is* read back later
(`src/rez/utils/sourcecode.py:339-344`) — but only to serve as a **cache key** into the in-memory
module dict:

```python
# src/rez/utils/sourcecode.py:357-365
module = self.modules.get(hash_str)
if module is not None:
    return module
...
module = load_module_from_file(name, filepath)
self.modules[hash_str] = module
```

The stored hash is **never** compared against a freshly computed hash of the file it describes. It is
content-addressing for a cache, not integrity verification.

So: a re-specification that adds artifact checksums, signature verification, or a download step is
**adding** capability, not porting it.

## 26. Artifact provenance metadata as a package-level concept

**ABSENT as a specified package-level concept.**
`ABSENT — searched: grep -rni "provenance\|source_url\|upstream_revision\|license"
src/rez/package_resources.py src/rez/package_maker.py src/rez/package_serialise.py`. The only hits are
the `SPDX-License-Identifier` file headers (e.g. `src/rez/package_resources.py:1`). There is no
`license`, no `source_url`, no `upstream_revision`, no `homepage` field in any package schema.

**What Rez does specify that is adjacent** — all of it *release* provenance, not *artifact* provenance:

| Attribute | Location | Notes |
|---|---|---|
| `revision` | `src/rez/package_resources.py:165` | `Optional('revision'): object` — deliberately untyped, because its shape is VCS-plugin-specific (`src/rez/release_vcs.py:150-154`). For git it is a dict with `commit`, `branch`, `tracking_branch`, `fetch_url`, `push_url` (`src/rezplugins/release_vcs/git.py:166-200`). |
| `previous_revision` | `:169` | Same untyped convention. |
| `previous_version` | `:168` | `Version`. |
| `changelog` | `:166` | `str`; truncated to `config.max_package_changelog_chars` (`src/rez/build_process.py:440-442`). |
| `release_message` | `:167` | `Or(None, str)`. |
| `vcs` | `:170` | `str` — **just the VCS plugin name**, e.g. `"git"` (`src/rez/build_process.py:444`). Not a URL. |
| `authors` | `:129` | `[str]`. |
| `uuid` | `:141` | `str`; used to stop unrelated same-named packages being released as one (`src/rez/build_process.py:331-337`). |

All seven release-time attributes are grouped in `package_release_keys` —
`src/rez/package_resources.py:32-39`.

**Ad-hoc provenance is possible but unspecified.** The package schema ends with a catch-all:

```python
# src/rez/package_resources.py:173
Optional(str):               late_bound(object)
```

so any attribute name is accepted. `rez pip` exploits exactly this to record provenance on
pip-derived packages — `from_pip`, `pip_name`, `is_pure_python`
(`src/rez/pip.py:438-440`) plus `help`/`authors` from distribution metadata (`:442-462`). These are
conventions of one plugin, **not** part of the specification; nothing validates or consumes them
generically.

## 27. Rez-native reproducible / deterministic builds

**ABSENT.** There is no concept of reproducible or deterministic *builds* in Rez 3.4.0.

`ABSENT — searched: grep -rni "SOURCE_DATE_EPOCH\|deterministic\|reproducible" src/ docs/
--include=*.py --include=*.rst --include=*.md`, excluding `vendor/`. Every hit is about **solve**
determinism or unrelated prose:

* `src/rez/solver.py:57` — "Solves are deterministic - given a known request and set of package
  repositories…".
* `src/rez/solver.py:753` — "the sort is necessary to ensure solves are deterministic".
* `src/rez/solver.py:1462` — "rez solves must be deterministic, so this is why we sort."
* `src/rez/util.py:206` — invalid variant indices "are sorted for deterministic error messages"
  (implementation `src/rez/util.py:213`).
* `src/rez/tests/test_util.py:79` — a test docstring about deterministic error messages.
* `docs/source/variants.rst:228` — "A resolve is still deterministic."
* `docs/source/guides/linking_to_rez_documentation.rst:65` — "reproducible documentation" (about
  docs builds, not packages).

Specifically absent:

1. **No fixed/overridable build timestamp in the reproducible-builds sense.** `timestamp` is
   `int(time.time())` at install time (`src/rezplugins/package_repository/filesystem.py:1435`, §A.9).
   It can be pinned only by the `overrides` dict on a *new* package
   (`filesystem.py:1423-1431`) — there is no `SOURCE_DATE_EPOCH` support and no `REZ_TIMESTAMP` env
   var.
2. **No deterministic payload ordering.** The build product is whatever the build system wrote;
   Rez copies it wholesale and records no manifest, no file list, and no per-file hashes
   (`src/rezplugins/build_process/local.py:283-305`, `:256-305`). The only per-file hash Rez writes is
   the `@include` sidecar described in §F.25, and it is a cache key.
3. **No build-input pinning beyond the resolve.** A build's inputs are captured only as the resolved
   context saved to `build.rxt` (`src/rezplugins/build_process/local.py:294-295`) and copied into the
   variant install dir (`:297-298`), plus `variant.json` (`:252-262`). These are debug aids —
   `variant.json` is documented as "there for debugging purposes only" (`:248-251`).

**Summary for auditors:** Rez guarantees *resolve* determinism, not *build* determinism. Any
reproducible-build story in a re-specification is new surface.

---

