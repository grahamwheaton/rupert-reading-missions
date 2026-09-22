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

import datetime
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys

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
    """Title and type from mission.json, falling back to the <title> tag."""
    meta = {}
    config = source / "mission.json"
    if config.is_file():
        meta = json.loads(config.read_text(encoding="utf-8"))

    title = meta.get("title")
    if not title:
        html = (source / "mission.html").read_text(encoding="utf-8", errors="replace")
        match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = match.group(1).strip() if match else mission_id
    return title, meta.get("type", "Fiction")


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


def main():
    mission_id, source = latest_mission()
    if not mission_id:
        print("no mission sources found; nothing to do")
        return

    current = PUBLISHED / "date.txt"
    if current.is_file() and current.read_text(encoding="utf-8").strip() == mission_id:
        print(f"{mission_id} is already published; nothing to do")
        return

    title, kind = metadata(source, mission_id)
    print(f"building {mission_id}: {title}")

    ARCHIVE.mkdir(parents=True, exist_ok=True)
    staged = ROOT / "today.mobi.part"
    try:
        convert(source, staged)
        size = validate(staged)
        digest = hashlib.sha256(staged.read_bytes()).hexdigest()
        shutil.copyfile(staged, ARCHIVE / f"{mission_id}.mobi")
        shutil.move(str(staged), PUBLISHED / "today.mobi")
    finally:
        staged.unlink(missing_ok=True)

    (PUBLISHED / "today.sha256").write_text(f"{digest}\n", encoding="utf-8")
    (PUBLISHED / "launcher.properties").write_text(
        f"id={mission_id}\ntitle={title}\ntype={kind}\nstreak={streak(mission_id)}\n",
        encoding="utf-8",
    )

    # Last. Everything above must exist before the Kindle is told to look.
    (PUBLISHED / "date.txt").write_text(f"{mission_id}\n", encoding="utf-8")

    print(f"published {mission_id} ({size} bytes, sha256 {digest})")


if __name__ == "__main__":
    main()
