"""Staged build.py entry point surviving rez-next's cleared child environment."""

from __future__ import annotations

import json
import os
import runpy
import sys
from pathlib import Path

CONTEXT_FILENAME = ".vx-build-environment.json"
SCRIPT_FILENAME = ".vx-original-build.py"
ENVIRONMENT_KEYS = frozenset(
    {
        "PATH",
        "TEMP",
        "TMP",
        "SystemRoot",
        "WINDIR",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
        "REZ_PACKAGES_PATH",
        "VX_BUILD_RECIPE",
        "VX_BUILD_TRIPLE",
    }
)


def main() -> None:
    directory = Path(__file__).resolve().parent
    context = json.loads(directory.joinpath(CONTEXT_FILENAME).read_text(encoding="utf-8"))
    if not isinstance(context, dict) or any(
        key not in ENVIRONMENT_KEYS or not isinstance(value, str) for key, value in context.items()
    ):
        raise ValueError("invalid wrapper build environment context")
    os.environ.update(context)
    script = directory / SCRIPT_FILENAME
    sys.argv[0] = str(script)
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
