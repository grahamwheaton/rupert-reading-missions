#!/usr/bin/env python3
"""Build the newest mission source into the published MOBI the Kindle fetches.

The Kindle reads `published/date.txt` first and only downloads
`published/today.mobi` when that ID changes. So the ID is written last, after
the book exists and has been validated: the pointer can never advance to a
book that was not built.

Mission sources are text only. Illustrations must be inline SVG or base64
`data:` URIs inside mission.html, because the scheduled job that pushes them
can write UTF-8 but not binary.
"""

import argparse
import datetime
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
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


def convert(source, destination):
    # Calibre picks the output plugin from the extension, so the destination
    # must end in .mobi -- staging to something like .part fails the run.
    assert destination.suffix == ".mobi", destination
    try:
        subprocess.run(
            ["ebook-convert", str(source / "mission.html"), str(destination)] + CONVERT,
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
    return size


def dry_run(source):
    """Convert and validate without touching published/. Proves the toolchain."""
    with tempfile.TemporaryDirectory() as workspace:
        book = pathlib.Path(workspace) / "dry-run.mobi"
        convert(source, book)
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

    current = PUBLISHED / "date.txt"
    if current.is_file() and current.read_text(encoding="utf-8").strip() == mission_id:
        print(f"{mission_id} is already published; nothing to do")
        return

    meta = metadata(source, mission_id)
    print(f"building {mission_id}: {meta['title']}")

    ARCHIVE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as workspace:
        staged = pathlib.Path(workspace) / "today.mobi"
        convert(source, staged)
        size = validate(staged)
        digest = hashlib.sha256(staged.read_bytes()).hexdigest()
        shutil.copyfile(staged, ARCHIVE / f"{mission_id}.mobi")
        shutil.copyfile(staged, PUBLISHED / "today.mobi")

    (PUBLISHED / "today.sha256").write_text(f"{digest}\n", encoding="utf-8")
    (PUBLISHED / "launcher.properties").write_text(
        launcher_properties(mission_id, meta), encoding="utf-8"
    )

    # Last. Everything above must exist before the Kindle is told to look.
    (PUBLISHED / "date.txt").write_text(f"{mission_id}\n", encoding="utf-8")

    print(f"published {mission_id} ({size} bytes, sha256 {digest})")


if __name__ == "__main__":
    main()
