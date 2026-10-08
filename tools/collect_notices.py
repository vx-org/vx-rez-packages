"""Collect actual license and notice texts from a digest-pinned upstream source archive."""

from __future__ import annotations

import argparse
import hashlib
import tempfile
from pathlib import Path

from tools.build_bundle import BundleError, _extract_archive, _verify_sha256


def collect_notices(source: Path, digest: str, source_url: str, destination: Path) -> str:
    """Write stable, unedited legal texts with upstream-relative source paths."""
    _verify_sha256(source, digest, "upstream source")
    sections = [f"Upstream source: {source_url}\nSHA-256: {digest}\n"]
    with tempfile.TemporaryDirectory(prefix="vx-rez-notices-") as temporary:
        extracted = Path(temporary) / "source"
        _extract_archive(source, extracted, "tar")
        for path in sorted(extracted.rglob("*"), key=lambda item: item.as_posix()):
            basename = path.name.upper()
            if not path.is_file() or path.is_symlink():
                continue
            if not any(
                basename == name or basename.startswith(name + ".")
                for name in ("LICENSE", "LICENCE", "NOTICE", "COPYING", "COPYRIGHT")
            ):
                continue
            text = path.read_text(encoding="utf-8")
            sections.append(
                f"\n{'=' * 72}\n{path.relative_to(extracted).as_posix()}\n"
                f"{'=' * 72}\n\n{text.rstrip()}\n"
            )
    if len(sections) == 1:
        raise BundleError("upstream source archive contains no legal notices")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(sections), encoding="utf-8", newline="\n")
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-archive", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(collect_notices(args.source_archive, args.sha256, args.source_url, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
