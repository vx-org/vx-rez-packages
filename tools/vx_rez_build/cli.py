"""Command line entry point for the ``rez build`` wrapper."""

from __future__ import annotations

import argparse
from pathlib import Path

from tools.vx_rez_build.builder import BuildError, build_variant, load_definition


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vx-rez-build",
        description="Build one recipe target with rez build and emit a packable repository.",
    )
    parser.add_argument("--definition", type=Path, required=True, help="path to recipe.json")
    parser.add_argument("--triple", required=True, help="target triple declared by the recipe")
    parser.add_argument("--output-dir", type=Path, required=True, help="where the repository lands")
    parser.add_argument(
        "--metadata-dir",
        type=Path,
        help="recipe directory holding package.py (default: recipe dir)",
    )
    parser.add_argument(
        "--sdk-executable", type=Path, help="rez SDK used for installation planning"
    )
    parser.add_argument(
        "--rez-executable", type=Path, help="rez binary (default: VX_REZ_EXECUTABLE)"
    )
    parser.add_argument(
        "--repository", type=Path, action="append", default=[], help="SDK dependency repository"
    )
    parser.add_argument("--source-dir", type=Path, help="package source root passed to rez build")
    args = parser.parse_args(argv)

    try:
        repository = build_variant(
            load_definition(args.definition),
            args.triple,
            args.output_dir,
            metadata_directory=args.metadata_dir or args.definition.parent,
            sdk_executable=args.sdk_executable,
            rez_executable=args.rez_executable,
            repositories=args.repository,
            source_directory=args.source_dir,
        )
    except (BuildError, OSError, ValueError, KeyError) as error:
        raise SystemExit(str(error)) from error
    print(repository)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
