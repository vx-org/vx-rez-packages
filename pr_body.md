## Summary

Defines the distributable artifact contract for Rez package bundles: the bundle
format plus the provider metadata a vx provider needs to consume them.

This addresses the capabilities described in vx#861 (discover versions from
release/index metadata, map vx platform/arch to bundle asset names, report
unsupported official platforms clearly) and provides the artifacts vx#860
downloads and extracts.

## The unpacked layout is part of the contract

`vx-rez-adapter` resolves environments through the rez-next SDK, whose resolve
step recognises exactly one repository layout:

```
<root>/<name>/<version>/package.py
```

So a bundle archive **wraps** a rez package root rather than replacing it, and
`bundle.json` declares where that root sits inside the archive (`rez.package_root`)
and where it must land (`rez.install_root`). Unpacking to
`<cache_root>/<name>/<version>/` lets `<cache_root>` be handed straight to the
adapter as a package path, which is what closes the vx#860 chain: download →
unpack to a stable cache location → resolve env → launch.

## What's included

- **`SPEC.md`** — naming rules, `bundle.json` and `index.json` field reference,
  unpack rules, verification steps, and a compatibility policy. Spec version
  `1.0.0-draft`; first release covers a single platform (`windows-x86_64`).
- **JSON Schemas** for both metadata files, plus `scripts/validate_repo.py`, a
  dependency-free validator covering the schema subset they use. It compares
  `index.json` against the index recomputed from the bundle tree, so the
  committed index cannot drift from the bundles.
- **A sample bundle** — `python` 3.11.9 for `windows-x86_64`, with buildable
  sources under `examples/`.
- **`scripts/make_bundle.py`** — packages a rez package tree into reproducible
  `tar.gz` and `zip` archives (verified byte-identical across rebuilds) and
  regenerates `index.json` as derived data.
- **CI** — validates bundles and index, asserts `index.json` is reproducible from
  the bundle tree, and proves the committed sample unpacks to the rez layout the
  adapter consumes.

## Verification

```
python scripts/validate_repo.py          # OK: 1 bundle(s) and index.json conform to spec
python -m unittest discover -s tests -v  # Ran 14 tests — OK
python scripts/release.py --dry-run      # verifies asset sizes and checksums
```

Both scripts use only the Python standard library (3.9+), so CI needs no install
step. Platform keys (`windows-x86_64`, `linux-aarch64`, …) reuse the vocabulary
vx already uses for `runtimes.layout.binary`, so no new mapping is introduced.

## Scope

This change is confined to the bundle format, sample, and generator. It does not
touch the vx repository, which is where the vx#860 consumer side lands.
