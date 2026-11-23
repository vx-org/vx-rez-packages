"""Wrap ``rez build`` so a VX Rez package builds itself from its own ``build.py``.

The published bundle contract is unchanged: this wrapper only replaces the
assembly half of ``tools/build_bundle.py``. Deterministic archiving, checksums
and consumer verification stay in the pack stage.
"""

from tools.vx_rez_build.builder import (
    BuildError,
    build_variant,
    load_definition,
)

__all__ = ["BuildError", "build_variant", "load_definition"]
