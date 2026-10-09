# Shared release catalog

Each Runtime repository owns its actual `package.py`, build recipe, native
validation, immutable bundle assets, and release index. The shared catalog
discovers those published release indexes across repositories.

```json
{
  "schema_version": 1,
  "releases": [
    {
      "tool": "example",
      "version": "1.2.3",
      "index_url": "https://github.com/vx-org/example/releases/download/example-1.2.3/index.json",
      "index_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }
  ]
}
```

This example is a format illustration. Its digest and release are placeholders.
The contract is [`catalog.schema.json`](../schema/catalog.schema.json) plus the
catalog validator: every `(tool, version)` identity must occur exactly once,
including when repeated entries have identical pins. URLs must use absolute
HTTPS without credentials or fragments. SHA-256 pins are lowercase hexadecimal.
Unknown fields and duplicate JSON object keys are rejected. Names and versions
are exact strings; the catalog does not interpret version expressions or aliases.

Maintain reviewed local JSON in this same format. Generation sorts entries by
`(tool, version)`, writes deterministic UTF-8 bytes with LF newlines, and emits
an adjacent checksum. It does not contact upstream services or bless unpublished
assets. Add an entry after the release workflow has published and read back the
index and its bundles successfully. Publish the catalog and checksum as a new
immutable asset, then distribute its exact URL and independently trusted digest
to consumers. Never silently replace a previously published identity or pin.

```console
vx uv run python -m tools.catalog validate --input reviewed-catalog.json
vx uv run python -m tools.catalog generate --input reviewed-catalog.json --output dist/catalog.json
```

`provision_from_catalog(catalog_url, catalog_sha256, cache, *, tool, version,
platform, arch, offline=False)` fetches and verifies the catalog using the
existing `cache_bundle._checked_download` contract. It selects exactly one
`(tool, version)` entry, then delegates to `cache_bundle.provision`. That existing
consumer validates the pinned release index, selects exactly one platform and
architecture bundle, verifies the archive and extracted repository, and returns
the repository path. The catalog itself is stored under `cache/catalogs/<sha256>`;
indexes, archives, and repositories use the existing cache layout.

```console
vx uv run python -m tools.catalog cache --catalog-url https://example.org/catalog.json --catalog-sha256 <trusted-sha256> --cache .cache/rez --tool example --version 1.2.3 --platform windows --arch x86_64
```

Add `--offline` to reuse the same pins without network access. A cache hit still
verifies every cached artifact and the repository contents. Missing or corrupted
data fails closed; offline mode never fetches replacements. A missing exact
version fails instead of selecting a nearby or newer version.

Rez Next's SDK consumes the returned repository and owns package reading,
dependency solving, variants, environment commands, isolation, and reversal.
The catalog has no solver, version resolver, package environment, or dependency
interpretation. For a dependency closure spanning several Runtime repositories,
the caller must first provision the pinned repositories needed by the SDK; this
catalog helper provisions one requested exact release at a time.

Catalog and cache contracts establish artifact discovery and verified local
repositories. They do not prove public publication, native application behavior,
or acceptance by an installed VX consumer. Record those delivery gates separately.
