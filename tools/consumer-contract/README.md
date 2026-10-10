# Native adapter consumer contract

This unpublished acceptance crate consumes the public `vx-rez-adapter` registry
crate. It contains no package parser, variant selector, solver or environment
interpreter. Update its exact adapter pin only after the reviewed version is
published, then generate and commit its Cargo lockfile before native CI uses
`--locked`.

From the shared tooling repository, build and test with:

```bash
vx cargo +1.95.0 test --manifest-path tools/consumer-contract/Cargo.toml --locked
vx cargo +1.95.0 build --manifest-path tools/consumer-contract/Cargo.toml --locked
```

The Python harness validates the declared native platform and hardware architecture,
verifies the complete repository and unchanged package definition against their
pins, and copies the repository to a private location before executing smoke tests.
Rust resolves that actual definition through the public adapter with an explicit
empty parent environment. It checks the manifest's selected variant root, executable
containment, and complete activated environment before launching the exact native
smoke command and its bare basename with identical arguments. Every launch must
exit successfully, and both outputs must contain the recipe's expected text.

The default package expectation is exactly `PATH`, in the order declared by
`package.path_entries`. These fields are verification expectations; the harness does
not turn them into package commands. Additional legitimate package variables require
an explicit `--expected-environment` JSON object containing the full package map,
including `PATH`. Values support the smoke command's `{root}`, `{version}` and
`{exe}` substitutions. The SDK's six documented `REZ_USED_*` metadata fields are
validated separately by their exact names and request/repository bindings. Other
parent variables fail; diagnostics print unexpected names without values.

For native CI before publication, verify and extract the real built bundle with:

```bash
vx uv run --locked python -m tools.verify_consumer --definition ../witr/recipe.json --triple x86_64-pc-windows-msvc --bundle-dir ../dist --consumer-executable "$CONSUMER_EXECUTABLE" --expected-sdk-version "$SDK_VERSION" --output ../receipts/native.json
```

This mode checks the archive's checksum companion, uses the cache utility's safe
extractor, then verifies the repository twice. It reports `source_kind: local_bundle`
and leaves the release asset directory unchanged. `--repository` also accepts an
already extracted, fully verified repository. These modes do not claim public
acquisition or an offline release-cache check.

After publication, use independently verified public index pins and a new cache:

```bash
vx uv run --locked python -m tools.verify_consumer --definition ../witr/recipe.json --triple x86_64-pc-windows-msvc --index-url "$INDEX_URL" --trusted-index ../trusted-release/index.json --cache .cache/native-consumer --require-empty-cache --consumer-executable "$CONSUMER_EXECUTABLE" --expected-sdk-version "$SDK_VERSION" --output ../receipts/public.json
```

The trusted local index and its checksum companion come from the index-generation
CI artifact. The harness checks those bytes before using that pin for public
acquisition; `--index-sha256` also accepts an independently verified digest directly.
The harness provisions through the existing verified cache utility, runs native
acceptance, re-reads the same pins with `offline=True`, and repeats native acceptance
from a new private copy. It preserves the cache and compares both observations.
`--offline` also supports rechecking an already provisioned cache, while
`--require-empty-cache` refuses to delete or reuse an existing cache. Receipts keep
stable repository-relative locations and environment names, rather than transient
paths or environment values.

The outer harness bounds each consumer process to twice the recipe smoke timeout
plus sixty seconds. Runner-level process-tree cleanup remains the CI runner's
responsibility. These are native adapter/SDK gates; installed VX acceptance is
separate.

The release workflow keeps native bundle, public asset readback, public acquisition
and offline cache evidence in separate gates. Native and public consumer receipts
are CI artifacts outside the release asset directory. Its native environment uses
an explicit Rust host toolchain, a pinned public SDK CLI, and the registry-only
adapter dependency recorded by this crate's lockfile.
