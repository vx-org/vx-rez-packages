# Specification-layer gap: deterministic / reproducible packaging

This is the one question the VX migration cannot answer by "sinking strategy into
`build.py`". It is answered here as a **specification-layer gap**, per the audit
constraint that no VX-side private protocol may be proposed as a fallback.

## What VX requires today

`tools/build_bundle.py` ends with a deterministic pack stage —
`_write_reproducible_tar_zst` and `_write_repository_checksums` — producing a
`.rez.tar.zst` whose entries are sorted and whose mtime/mode/uid are normalised,
plus `sha256sums.txt`, `manifest.json` and `provenance.json` inside the package.
The builder's own header describes the output as deterministic, and each recipe
pins its upstream artifact by SHA-256 (`schema/bundle-definition.schema.json`,
`targets[].upstream.sha256`).

Two separable requirements hide inside that:

1. **Payload determinism** — same inputs ⇒ byte-identical archive.
2. **Provenance** — the artifact records where it came from and what it hashes to.

## Rez side, verified against upstream Rez 3.4.0

### `timestamp` is the only provenance field Rez records

`src/rez/package_resources.py:32-39`:

```python
package_release_keys = (
    "timestamp",
    'revision',
    'changelog',
    'release_message',
    'previous_version',
    'previous_revision',
    'vcs')
```

There is no `built_by`, `build_user`, `build_host` or `build_time` — a grep for
those across `src/rez` and `src/rezplugins` returns zero hits in Rez's own code.

### The value is `int(time.time())`, unconditionally

`src/rezplugins/package_repository/filesystem.py:1433-1435`:

```python
# timestamp defaults to now if not specified
if not package_data.get("timestamp"):
    package_data["timestamp"] = int(time.time())
```

`get_release_data()` (`src/rez/build_process.py:414-448`) returns only `vcs`,
`revision`, `changelog`, `previous_version`, `previous_revision` — never a
timestamp — so the release path always falls through to `int(time.time())`.

### There is no control over it

- **`SOURCE_DATE_EPOCH` is not supported.** No hit anywhere in Rez's own code;
  the only match in the distribution is vendored third-party code
  (`src/rez/vendor/distlib/scripts.py:270`).
- **No config setting.** `src/rez/config.py` declares exactly two `build_*`
  settings — `build_directory` (`:409`) and `build_thread_count` (`:451`). The
  build-process plugin contributes none. The only timestamp-adjacent setting is
  `warn_untimestamped` (`src/rez/config.py:480`), a warning toggle.
- **No CLI flag.** `rez build` and `rez release` expose no `--timestamp`.
- The only affordance is `rez cp --keep-timestamp`
  (`src/rez/package_copy.py:236-237`, `src/rez/cli/cp.py:41-42`), which
  **preserves** an existing timestamp on a copy. It cannot pin an arbitrary one,
  and it does not exist on the build or release path.

### The one path that could pin it is `install_variant`'s `overrides`

`install_variant(..., overrides={"timestamp": N})` can set it — but the override
is deliberately ignored for an existing package
(`src/rezplugins/package_repository/filesystem.py:1414-1431`): *"This is done so
that variants added to an existing package don't change attributes such as
'timestamp'."*

And that operation is exactly the one rez-next does not implement — see
[`05-headline-verdict.md`](05-headline-verdict.md) and
[rez-next#332](https://github.com/vx-org/rez-next/issues/332). rez-next also
excludes the copy-side timestamp option
(`docs/production-readiness.md:39-40`, "timestamp preservation … rejected").

### Rez has no artifact-checksum facility

Every `hashlib` use in `src/rez` is internal — SHA-1 for payload identity,
package-cache keys and source-code fingerprints
(`src/rez/package_cache.py:11`, `src/rez/package_filter.py:12`,
`src/rez/package_order.py:8`, `src/rez/package_resources.py:23`,
`src/rez/resolver.py:17`, `src/rez/utils/sourcecode.py:313`). There is no
user-facing "verify this downloaded artifact against this digest" step anywhere
in the build or install path.

`sha256sums.txt`, `manifest.json` and `provenance.json` have no Rez equivalent.

## Conclusion

| VX requirement | Rez-spec home | Status |
|---|---|---|
| Multi-platform target matrix | `variants` + `platform-<p>/arch-<a>` subpath | **Mappable** — aligned, see `05-headline-verdict.md` |
| Pinned upstream URL + SHA-256 + prefix strip | none in spec | **Build-logic** — sinks into `build.py`; rez-next's `binary_archive` is a non-spec convenience |
| File-mode / executable bit | none in spec | **Build-logic** — `build.py` |
| `build_time` determinism | `timestamp` (int epoch) exists, but is unconditionally `int(time.time())` on build/release | **Spec-layer gap** |
| Byte-identical archive (sorted, normalised mtime/mode/uid, `.tar.zst`) | none in spec | **Spec-layer gap** |
| `sha256sums.txt` | none in spec | **Spec-layer gap** |
| `manifest.json`, `provenance.json` | none in spec (`package_release_keys` has no such fields) | **Spec-layer gap** |
| `LICENSE`, `THIRD_PARTY_NOTICES.txt` | ordinary payload files | **Mappable** — Rez imposes nothing on extra files |

**Deterministic packaging cannot be expressed entirely in Rez-native terms.**
The strategy half sinks cleanly into `build.py` under the Rez `build_system` /
`build_command` protocol; the *reproducibility and provenance* half has no home in
the Rez specification.

Per the audit constraint, **no VX-side private fallback is proposed here.** This
is recorded as a specification-layer gap and must be adjudicated by product. The
question to decide is whether VX's published schema-v1 artifacts
(`sha256sums.txt`, `manifest.json`, `provenance.json`, deterministic `.tar.zst`)
remain a VX publication-layer contract outside the Rez package itself — which is
defensible, because they describe the **release channel**, not the package — or
whether they are folded into package payload metadata instead.
