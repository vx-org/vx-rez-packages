"""Print the supported target matrix consumed by GitHub Actions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.build_bundle import load_definition


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", type=Path, required=True)
    args = parser.parse_args()
    definition = load_definition(args.definition)
    matrix = [
        {
            "triple": target["triple"],
            "runner": target["runner"],
            "platform": target["platform"],
            "arch": target["arch"],
        }
        for target in definition["targets"]
    ]
    print(json.dumps(matrix, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
