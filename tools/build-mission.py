#!/usr/bin/env python3
"""Build the newest mission source into the published MOBI the Kindle fetches.

The Kindle reads `published/date.txt` first and only downloads
`published/today.mobi` when that ID changes. So the ID is written last, after
the book exists and has been validated: the pointer can never advance to a
book that was not built.

Mission sources are text only. A required 600x800, 8-bit greyscale cover is
carried in cover.png.base64, wrapped at 76 characters per line. The title is
the only text in the approved artwork.
"""

import argparse
import base64
import binascii
import datetime
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import struct
import zlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
MISSIONS = ROOT / "missions"
PUBLISHED = ROOT / "published"
ARCHIVE = PUBLISHED / "archive"

# The K4 needs legacy MOBI 6; KF8 will not open on firmware 4.1.4.
CONVERT = ["--mobi-file-type", "old", "--output-profile", "kindle"]

# The device sync rejects anything smaller than this as a failed download.
MIN_BYTES = 1024

DATED_DIR = re.compile(r"^(\d{4}-\d{2}-\d{2})-")


def latest_mission():
    """Newest missions/<YYYY-MM-DD>-<slug>/ directory, by date prefix."""
    candidates = []
    for path in MISSIONS.iterdir():
        if not path.is_dir():
            continue
        match = DATED_DIR.match(path.name)
        if match and (path / "mission.html").is_file():
            candidates.append((match.group(1), path))
    if not candidates:
        return None, None
    return max(candidates, key=lambda item: (item[0], item[1].name))


def metadata(source, mission_id):
    """mission.json, with the title falling back to the <title> tag."""
    meta = {}
    config = source / "mission.json"
    if config.is_file():
        meta = json.loads(config.read_text(encoding="utf-8"))

    if not meta.get("title"):
        html = (source / "mission.html").read_text(encoding="utf-8", errors="replace")
        match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        meta["title"] = match.group(1).strip() if match else mission_id
    meta.setdefault("type", "Fiction")
    return meta


def mission_number(mission_id):
    """How many missions have been published, counting this one."""
    published = {mission_id}
    if ARCHIVE.is_dir():
        published.update(path.stem for path in ARCHIVE.glob("*.mobi"))
    return len(published)


def one_line(value):
    """launcher.properties is one key per line, so flatten any whitespace."""
    return re.sub(r"\s+", " ", str(value)).strip()


def launcher_properties(mission_id, meta):
    """The fields the Kindle dashboard reads. Everything but id/title/type/
    streak is optional; the dashboard falls back when a key is missing."""
    fields = [
        ("id", mission_id),
        ("title", meta["title"]),
        ("type", meta["type"]),
        ("streak", streak(mission_id)),
        ("mission", meta.get("mission") or mission_number(mission_id)),
    ]
    for key in ("subtitle", "blurb"):
        if meta.get(key):
            fields.append((key, meta[key]))

    # tags: [{"icon": "terrain", "text": "4x4s"}, ...] -- icon is one of
    # terrain, wrench, book, star; anything else is ignored by the dashboard.
    for index, tag in enumerate(meta.get("tags", [])[:4], start=1):
        icon = one_line(tag.get("icon", "star"))
        text = one_line(tag.get("text", ""))
        if text:
            fields.append((f"tag{index}", f"{icon}|{text}"))

    return "".join(f"{key}={one_line(value)}\n" for key, value in fields)


def streak(mission_id):
    """Consecutive days of missions ending at mission_id."""
    dates = {mission_id}
    if ARCHIVE.is_dir():
        for path in ARCHIVE.glob("*.mobi"):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.stem):
                dates.add(path.stem)

    day = datetime.date.fromisoformat(mission_id)
    count = 0
    while day.isoformat() in dates:
        count += 1
        day -= datetime.timedelta(days=1)
    return count


def source_fingerprint(source):
    """Digest of the mission's sources, so a corrected story is republished.

    The ID alone is not enough: fixing today's mission leaves the ID the same,
    and the Kindle would keep the first version forever.
    """
    digest = hashlib.sha256()
    for name in ("mission.html", "mission.json", "cover.png.base64"):
        path = source / name
        digest.update(path.read_bytes() if path.is_file() else b"")
    return digest.hexdigest()


def decode_cover(source, destination):
    """Require a complete, Kindle-sized greyscale PNG carried as wrapped text."""
    encoded = source / "cover.png.base64"
    if not encoded.is_file():
        sys.exit(f"refusing to publish: missing {encoded}")
    lines = encoded.read_text(encoding="ascii").splitlines()
    if not lines or any(not line or len(line) > 76 for line in lines):
        sys.exit("refusing to publish: cover base64 must be wrapped at 76 characters")
    payload = "".join(lines)
    if len(payload) % 4:
        sys.exit("refusing to publish: cover base64 length is not divisible by four")
    try:
        data = base64.b64decode(payload, validate=True)
    except binascii.Error as error:
        sys.exit(f"refusing to publish: invalid cover base64 ({error})")
    if len(data) < 57 or not data.startswith(b"\\x89PNG\\r\\n\\x1a\\n"):
        sys.exit("refusing to publish: cover is not a PNG")
    pos, has_image, has_end = 8, False, False
    while pos + 12 <= len(data):
        length = struct.unpack_from(">I", data, pos)[0]
        end = pos + 12 + length
        if end > len(data):
            sys.exit("refusing to publish: truncated cover PNG")
        kind = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        crc = struct.unpack_from(">I", data, pos + 8 + length)[0]
        if zlib.crc32(kind + chunk) & 0xffffffff != crc:
            sys.exit("refusing to publish: cover PNG checksum failed")
        if kind == b"IHDR":
            width, height, depth, colour = struct.unpack_from(">IIBB", chunk)
            if (width, height, depth, colour) != (600, 800, 8, 0):
                sys.exit("refusing to publish: cover must be 600x800, 8-bit greyscale PNG")
        elif kind == b"IDAT":
            has_image = True
        elif kind == b"IEND":
            has_end = end == len(data)
            break
        pos = end
    if not (has_image and has_end):
        sys.exit("refusing to publish: cover PNG is incomplete")
    destination.write_bytes(data)


def convert(source, destination, cover):
    # Calibre picks the output plugin from the extension, so the destination
    # must end in .mobi -- staging to something like .part fails the run.
    assert destination.suffix == ".mobi", destination
    try:
        subprocess.run(
            ["ebook-convert", str(source / "mission.html"), str(destination)] + CONVERT + ["--cover", str(cover)],
            check=True,
        )
    except subprocess.CalledProcessError as error:
        sys.exit(f"refusing to publish: ebook-convert failed ({error.returncode})")


def validate(book):
    size = book.stat().st_size
    if size < MIN_BYTES:
        sys.exit(f"refusing to publish: only {size} bytes, device would reject it")
    # MOBI 6 carries the PalmDB type/creator at offset 60.
    with book.open("rb") as handle:
        handle.seek(60)
        if handle.read(8) != b"BOOKMOBI":
            sys.exit("refusing to publish: output is not a MOBI 6 book")
    data = book.read_bytes()
    count = struct.unpack_from(">H", data, 76)[0]
    offsets = [struct.unpack_from(">I", data, 78 + 8 * i)[0] for i in range(count)]
    if not offsets or offsets[0] + 112 > len(data):
        sys.exit("refusing to publish: MOBI record table is incomplete")
    first_image = struct.unpack_from(">I", data, offsets[0] + 108)[0]
    if first_image >= count or not any(
        data[offsets[i]:offsets[i] + 4].startswith((b"\\xff\\xd8\\xff", b"\\x89PNG", b"GIF"))
        for i in range(first_image, count)
    ):
        sys.exit("refusing to publish: MOBI contains no cover image")
    return size


def dry_run(source):
    """Convert and validate without touching published/. Proves the toolchain."""
    with tempfile.TemporaryDirectory() as workspace:
        book = pathlib.Path(workspace) / "dry-run.mobi"
        cover = pathlib.Path(workspace) / "cover.png"
        decode_cover(source, cover)
        convert(source, book, cover)
        size = validate(book)
        print(f"dry run OK: {source.name} converts to a {size} byte MOBI 6 book")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        help="mission directory to build (default: the newest dated one)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="convert and validate only; publish nothing",
    )
    args = parser.parse_args()

    if args.source:
        source = pathlib.Path(args.source)
        if not (source / "mission.html").is_file():
            sys.exit(f"no mission.html in {source}")
        if args.dry_run:
            dry_run(source)
            return
        match = DATED_DIR.match(source.name)
        if not match:
            sys.exit(f"{source.name} has no YYYY-MM-DD prefix; use --dry-run")
        mission_id = match.group(1)
    else:
        mission_id, source = latest_mission()
        if not mission_id:
            print("no mission sources found; nothing to do")
            return
        if args.dry_run:
            dry_run(source)
            return

    fingerprint = source_fingerprint(source)
    published_id = PUBLISHED / "date.txt"
    published_fingerprint = PUBLISHED / "source.sha256"
    if (
        published_id.is_file()
        and published_id.read_text(encoding="utf-8").strip() == mission_id
        and published_fingerprint.is_file()
        and published_fingerprint.read_text(encoding="utf-8").strip() == fingerprint
    ):
        print(f"{mission_id} is already published and unchanged; nothing to do")
        return

    meta = metadata(source, mission_id)
    print(f"building {mission_id}: {meta['title']}")

    ARCHIVE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as workspace:
        staged = pathlib.Path(workspace) / "today.mobi"
        cover = pathlib.Path(workspace) / "cover.png"
        decode_cover(source, cover)
        convert(source, staged, cover)
        size = validate(staged)
        digest = hashlib.sha256(staged.read_bytes()).hexdigest()
        shutil.copyfile(staged, ARCHIVE / f"{mission_id}.mobi")
        shutil.copyfile(staged, PUBLISHED / "today.mobi")

    (PUBLISHED / "today.sha256").write_text(f"{digest}\n", encoding="utf-8")
    published_fingerprint.write_text(f"{fingerprint}\n", encoding="utf-8")
    (PUBLISHED / "launcher.properties").write_text(
        launcher_properties(mission_id, meta), encoding="utf-8"
    )

    # Last. Everything above must exist before the Kindle is told to look.
    (PUBLISHED / "date.txt").write_text(f"{mission_id}\n", encoding="utf-8")

    print(f"published {mission_id} ({size} bytes, sha256 {digest})")


if __name__ == "__main__":
    main()
