#!/usr/bin/env python3
"""Split a PNG into GitHub connector friendly UTF-8 cover parts.

Usage: python3 tools/encode-cover.py cover.png missions/YYYY-MM-DD-slug
The PNG is checked by build-mission.py; this only transports its bytes safely.
"""
import argparse
import base64
import pathlib
import textwrap

LINES_PER_PART = 180  # 13.7 KB per file, safely below text connector limits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=pathlib.Path)
    parser.add_argument("mission", type=pathlib.Path)
    args = parser.parse_args()
    if not args.image.is_file() or not args.mission.is_dir():
        parser.error("the PNG and mission directory must already exist")
    lines = textwrap.wrap(base64.b64encode(args.image.read_bytes()).decode("ascii"), 76)
    parts = [lines[i:i + LINES_PER_PART] for i in range(0, len(lines), LINES_PER_PART)]
    if len(parts) > 99:
        parser.error("cover is too large for 99 parts")
    if (args.mission / "cover.png.base64").exists():
        parser.error("remove the old single-file cover before writing parts")
    for old in args.mission.glob("cover.png.base64.part*"):
        old.unlink()
    for index, part in enumerate(parts, 1):
        target = args.mission / f"cover.png.base64.part{index:02d}"
        target.write_text("\n".join(part) + "\n", encoding="ascii")
        print(f"{target}: {target.stat().st_size} bytes")


if __name__ == "__main__":
    main()
