#!/usr/bin/env python3
"""Publish unchecked ActionNotes rewards as a Kindle-safe store catalog.

Usage: python3 tools/build-unlocks.py --notes /path/to/SharedProjectNotes
"""
import argparse
import hashlib
import math
import pathlib
import re
import sys
from decimal import Decimal, ROUND_CEILING

from PIL import Image, ImageOps

ROOT = pathlib.Path(__file__).resolve().parents[1]
TASK = re.compile(r"^- \[([ xX])\] (.+?)\s*$")
IMAGE = re.compile(r"!\[[^]]*\]\(([^)]+)\)")
PRICE = re.compile(r"£\s*(\d+(?:\.\d{1,2})?)\b")
ALLOWED = re.compile(r"^[a-z0-9][a-z0-9-]{0,90}$")


def parse_note(text):
    items = []
    current = None
    for line in text.splitlines() + ["- [x] end"]:
        match = TASK.match(line)
        if match:
            if current and not current["done"]:
                items.append(current)
            current = {"done": match.group(1).lower() == "x",
                       "title": match.group(2).strip(), "image": None, "price": None}
            continue
        if not current:
            continue
        picture = IMAGE.search(line)
        if picture and current["image"] is None:
            current["image"] = picture.group(1)
        price = PRICE.search(line)
        if price and current["price"] is None:
            current["price"] = Decimal(price.group(1))
    return items


def build(notes, output):
    note = (notes / "projects/rupertunlocks.md").resolve()
    entries = parse_note(note.read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=True)
    pictures = output / "images"
    pictures.mkdir(exist_ok=True)
    rows = []
    ids = set()
    for item in entries:
        title = item["title"]
        if not item["image"] or item["price"] is None:
            raise ValueError(f"Unfinished reward needs a picture and a £ price: {title}")
        if any(c in title for c in "\t\r\n|"):
            raise ValueError(f"Invalid title: {title}")
        # The attachment path is stable when the title or price is edited.
        name = pathlib.PurePosixPath(item["image"]).name
        ident = re.sub("[^a-z0-9-]+", "-", pathlib.Path(name).stem.lower()).strip("-")
        ident = "reward-" + ident
        if not ALLOWED.fullmatch(ident) or ident in ids:
            raise ValueError(f"Duplicate or invalid image filename: {name}")
        ids.add(ident)
        source = (note.parent / item["image"]).resolve()
        if not source.is_relative_to(notes.resolve()) or not source.is_file():
            raise ValueError(f"Missing or unsafe attachment: {item['image']}")
        pence = int(item["price"] * 100)
        if pence <= 0:
            raise ValueError(f"Price must be positive: {title}")
        points = int((item["price"] * 5).to_integral_value(rounding=ROUND_CEILING))
        target = pictures / (ident + ".png")
        with Image.open(source) as raw:
            picture = ImageOps.exif_transpose(raw).convert("RGB")
            # Preserve words embedded in cover art; a centre crop can remove
            # the season/title from wide screenshots. Fill the square instead.
            picture = ImageOps.pad(picture, (220, 220),
                                   method=Image.Resampling.LANCZOS, color="#eeeeee")
            picture = picture.convert("L").quantize(colors=16).convert("L")
            picture.save(target, format="PNG", optimize=True)
        sha = hashlib.sha256(target.read_bytes()).hexdigest()
        rows.append(f"{ident}\t{pence}\t{points}\t{title}\t{sha}")
    # Remove thumbnails of completed/deleted entries on each publish.
    for old in pictures.glob("*.png"):
        if old.stem not in ids:
            old.unlink()
    data = ("\n".join(rows) + "\n").encode("utf-8")
    (output / "catalog.tsv").write_bytes(data)
    (output / "catalog.sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
    print(f"Published {len(rows)} unlocks")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notes", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, default=ROOT / "published/unlocks")
    args = parser.parse_args()
    try:
        build(args.notes, args.output)
    except (OSError, ValueError) as exc:
        sys.exit(f"Cannot publish unlocks: {exc}")
