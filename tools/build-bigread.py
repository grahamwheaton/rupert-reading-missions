#!/usr/bin/env python3
"""Validate and publish the newest Big Read: the weekly interactive story.

Unlike a mission, a Big Read is not a book. The Kindle renders it itself so it
can offer choices, so what ships is the story's JSON and its pictures packed
into one tar. The ID is written last, after the tar and its digest exist, so
the Kindle can never be pointed at a story that is still half-published.

Every rule here exists because a seven-year-old meets the result: pages that
fit the screen, choices that go somewhere, and no branch that traps him.
"""

import argparse
import base64
import binascii
import hashlib
import io
import json
import pathlib
import re
import struct
import sys
import tarfile
import tempfile
import zlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
BIGREADS = ROOT / "bigreads"
PUBLISHED = ROOT / "published"

DATED_DIR = re.compile(r"^(\d{4}-\d{2}-\d{2})-")
NODE_ID = re.compile(r"^[a-z0-9-]+$")

# A page holds about twenty lines at his reading size, and the choices take the
# bottom of the screen.
WORDS_WITH_IMAGE = (20, 70)
WORDS_WITHOUT_IMAGE = (25, 110)
CHOICE_CHARS = 40
NODES = (20, 60)
MIN_ENDINGS = 3

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
MAX_IMAGE = (600, 500)
MAX_COVER = (600, 800)
MAX_TOTAL_BYTES = 4 * 1024 * 1024


def latest_bigread():
    candidates = []
    if not BIGREADS.is_dir():
        return None, None
    for path in BIGREADS.iterdir():
        match = DATED_DIR.match(path.name) if path.is_dir() else None
        if match and (path / "story.json").is_file():
            candidates.append((match.group(1), path))
    if not candidates:
        return None, None
    return max(candidates, key=lambda item: (item[0], item[1].name))


def image_bytes(source, name):
    """A picture's bytes, from the file itself or from <name>.base64.

    The job that writes stories can push text but not binary, which is how a
    cover arrived truncated once, so base64 beside story.json is the safer
    route and the one the README asks for.
    """
    encoded = source / (name + ".base64")
    if encoded.is_file():
        # Line breaks are fine and in fact safer: a single enormous line is
        # easily mangled in transit.
        text = "".join(encoded.read_text(encoding="utf-8").split())
        if len(text) % 4:
            raise ValueError(
                f"'{name}.base64' is {len(text)} characters, which is not a whole number of "
                "4-character groups, so characters were lost on the way here. Write it again, "
                "wrapped at 76 characters per line")
        try:
            return base64.b64decode(text, validate=True), "base64"
        except (binascii.Error, ValueError) as error:
            raise ValueError(f"'{name}.base64' is not valid base64: {error}") from error
    path = source / name
    if path.is_file():
        return path.read_bytes(), "binary"
    return None, None


def check_png(data):
    """Every problem with a PNG's structure, walking its chunks."""
    if len(data) < 8 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return ["is not a PNG"], None
    problems, size, offset, saw_end = [], None, 8, False
    idat = b""
    while offset + 8 <= len(data):
        length = int.from_bytes(data[offset:offset + 4], "big")
        tag = data[offset + 4:offset + 8]
        if offset + 12 + length > len(data):
            problems.append(f"is truncated: the {tag.decode('ascii', 'replace')} chunk needs "
                            f"{length} bytes but the file ends")
            break
        body = data[offset + 8:offset + 8 + length]
        crc = int.from_bytes(data[offset + 8 + length:offset + 12 + length], "big")
        if crc != binascii.crc32(tag + body):
            problems.append(f"is corrupt: the {tag.decode('ascii', 'replace')} chunk fails its checksum")
        if tag == b"IHDR" and length >= 8:
            size = struct.unpack(">II", body[:8])
        elif tag == b"IDAT":
            idat += body
        elif tag == b"IEND":
            saw_end = True
            break
        offset += 12 + length
    if not saw_end and not problems:
        problems.append("is truncated: it has no end marker")
    if idat and not problems:
        try:
            zlib.decompress(idat)
        except zlib.error as error:
            problems.append(f"will not decode: {error}")
    return problems, size


def check_jpeg(data):
    """Size and basic integrity of a JPEG."""
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return ["is not a JPEG"], None
    if data[-2:] != b"\xff\xd9":
        return ["is truncated: it has no end marker"], None
    offset, size = 2, None
    while offset < len(data) - 9:
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        length = int.from_bytes(data[offset + 2:offset + 4], "big")
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB):
            size = (int.from_bytes(data[offset + 7:offset + 9], "big"),
                    int.from_bytes(data[offset + 5:offset + 7], "big"))
            break
        offset += 2 + length
    return [], size


def image_size(path):
    """Width and height of a PNG or JPEG, without needing Pillow on the runner."""
    data = path.read_bytes()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data[:2] == b"\xff\xd8":
        offset = 2
        while offset < len(data) - 9:
            if data[offset] != 0xFF:
                offset += 1
                continue
            marker = data[offset + 1]
            length = int.from_bytes(data[offset + 2:offset + 4], "big")
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB):
                height = int.from_bytes(data[offset + 5:offset + 7], "big")
                width = int.from_bytes(data[offset + 7:offset + 9], "big")
                return width, height
            offset += 2 + length
    return None


def words(text):
    return len(text.split())


def reachable_from(nodes, start):
    seen, queue = set(), [start]
    while queue:
        node_id = queue.pop()
        if node_id in seen or node_id not in nodes:
            continue
        seen.add(node_id)
        for choice in nodes[node_id].get("choices", []):
            queue.append(choice.get("next"))
    return seen


def can_reach_ending(nodes):
    """Node IDs from which an ending is reachable, grown backwards from endings."""
    good = {node_id for node_id, node in nodes.items() if node.get("ending")}
    changed = True
    while changed:
        changed = False
        for node_id, node in nodes.items():
            if node_id in good:
                continue
            for choice in node.get("choices", []):
                if choice.get("next") in good:
                    good.add(node_id)
                    changed = True
                    break
    return good


def validate(source):
    """Every problem with a story, as a list of sentences. Empty means good."""
    problems = []
    try:
        story = json.loads((source / "story.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"story.json could not be read: {error}"], None, {}

    for key in ("title", "subtitle", "cover", "start", "nodes"):
        if not story.get(key):
            problems.append(f"story.json has no {key}")
    if problems:
        return problems, story, {}

    nodes = story["nodes"]
    if not isinstance(nodes, dict):
        return ["nodes must be an object keyed by node ID"], story, {}

    if not NODES[0] <= len(nodes) <= NODES[1]:
        problems.append(f"{len(nodes)} nodes; a Big Read has between {NODES[0]} and {NODES[1]}")
    if story["start"] not in nodes:
        problems.append(f"start node '{story['start']}' does not exist")

    images = {story["cover"]}
    endings = 0
    for node_id, node in sorted(nodes.items()):
        where = f"node '{node_id}'"
        if not NODE_ID.match(node_id):
            problems.append(f"{where}: IDs use lowercase letters, numbers and hyphens")
        text = node.get("text", "")
        if not text.strip():
            problems.append(f"{where}: has no text")
            continue

        if node.get("image"):
            images.add(node["image"])
            low, high = WORDS_WITH_IMAGE
        else:
            low, high = WORDS_WITHOUT_IMAGE
        count = words(text)
        if count > high:
            problems.append(f"{where}: {count} words, at most {high} fit on the page")
        elif count < low and not node.get("ending"):
            # An ending is often a short last beat, so only the limit applies.
            problems.append(f"{where}: only {count} words; pages run {low} to {high}")

        if node.get("ending"):
            endings += 1
            if node.get("choices"):
                problems.append(f"{where}: an ending cannot also offer choices")
            continue

        choices = node.get("choices") or []
        if len(choices) != 2:
            problems.append(f"{where}: {len(choices)} choices; a page offers exactly two")
        for index, choice in enumerate(choices, start=1):
            label = (choice.get("text") or "").strip()
            if not label:
                problems.append(f"{where}: choice {index} has no text")
            elif len(label) > CHOICE_CHARS:
                problems.append(
                    f"{where}: choice {index} is {len(label)} characters, at most {CHOICE_CHARS} fit")
            target = choice.get("next")
            if target not in nodes:
                problems.append(f"{where}: choice {index} leads to '{target}', which does not exist")

    if endings < MIN_ENDINGS:
        problems.append(f"{endings} endings; a Big Read has at least {MIN_ENDINGS}")

    if story["start"] in nodes:
        seen = reachable_from(nodes, story["start"])
        for node_id in sorted(set(nodes) - seen):
            problems.append(f"node '{node_id}' cannot be reached from the start")
        dead = seen - can_reach_ending(nodes)
        for node_id in sorted(dead):
            problems.append(f"node '{node_id}': no ending can be reached from here")

    total = 0
    pictures = {}
    for name in sorted(images):
        if pathlib.Path(name).suffix.lower() not in IMAGE_SUFFIXES:
            problems.append(f"picture '{name}': use PNG or JPEG")
            continue
        try:
            data, how = image_bytes(source, name)
        except ValueError as error:
            problems.append(f"picture {error}")
            continue
        if data is None:
            problems.append(f"picture '{name}' is missing (as itself or as {name}.base64)")
            continue

        # Decode it rather than trusting the header: a truncated cover with a
        # valid header is exactly how a broken story reached the Kindle once.
        if name.lower().endswith(".png"):
            faults, size = check_png(data)
        else:
            faults, size = check_jpeg(data)
        for fault in faults:
            problems.append(f"picture '{name}' {fault}" + (f" (pushed as {how})" if how else ""))
        if faults:
            continue

        total += len(data)
        limit = MAX_COVER if name == story["cover"] else MAX_IMAGE
        if size and (size[0] > limit[0] or size[1] > limit[1]):
            problems.append(
                f"picture '{name}' is {size[0]}x{size[1]}, at most {limit[0]}x{limit[1]}")
        pictures[name] = data

    total += (source / "story.json").stat().st_size
    if total > MAX_TOTAL_BYTES:
        problems.append(f"the story is {total // 1024} KB; keep it under {MAX_TOTAL_BYTES // 1024} KB")

    return problems, story, pictures


def print_map(story):
    nodes = story["nodes"]
    print(f"{story['title']} - {len(nodes)} nodes, start at '{story['start']}'")
    for node_id, node in sorted(nodes.items()):
        mark = "*" if node_id == story["start"] else " "
        picture = " [picture]" if node.get("image") else ""
        if node.get("ending"):
            print(f"{mark} {node_id}: ENDING - {node['ending']}{picture}")
        else:
            print(f"{mark} {node_id}:{picture}")
            for choice in node.get("choices", []):
                print(f"      {choice.get('text')} -> {choice.get('next')}")


def publish(bigread_id, source, story, pictures):
    PUBLISHED.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as workspace:
        staged = pathlib.Path(workspace) / "bigread.tar"
        # BusyBox 1.7.2 on the Kindle warns at PAX headers, which is what
        # Python writes by default; the old format it understands is enough.
        with tarfile.open(staged, "w", format=tarfile.USTAR_FORMAT) as archive:
            archive.add(source / "story.json", arcname="story.json")
            for name in sorted(pictures):
                info = tarfile.TarInfo(name)
                info.size = len(pictures[name])
                archive.addfile(info, io.BytesIO(pictures[name]))
        data = staged.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        (PUBLISHED / "bigread.tar").write_bytes(data)

    (PUBLISHED / "bigread.sha256").write_text(f"{digest}\n", encoding="utf-8")
    # Last: everything above must exist before the Kindle is told to look.
    (PUBLISHED / "bigread.txt").write_text(f"{bigread_id}\n", encoding="utf-8")
    print(f"published {bigread_id} ({len(data)} bytes, sha256 {digest})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", metavar="DIR", help="validate a story and publish nothing")
    parser.add_argument("--map", action="store_true", help="print the story's shape")
    args = parser.parse_args()

    if args.check:
        source = pathlib.Path(args.check)
        bigread_id = None
    else:
        bigread_id, source = latest_bigread()
        if not bigread_id:
            print("no Big Read sources found; nothing to do")
            return

    problems, story, pictures = validate(source)
    if problems:
        print(f"refusing to publish {source.name}:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        sys.exit(1)
    print(f"{source.name} is good: {len(story['nodes'])} nodes")
    if args.map:
        print_map(story)
    if args.check:
        return

    current = PUBLISHED / "bigread.txt"
    fingerprint = hashlib.sha256()
    for path in sorted(source.rglob("*")):
        if path.is_file():
            fingerprint.update(path.name.encode())
            fingerprint.update(path.read_bytes())
    marker = PUBLISHED / "bigread-source.sha256"
    if (current.is_file() and current.read_text(encoding="utf-8").strip() == bigread_id
            and marker.is_file() and marker.read_text(encoding="utf-8").strip() == fingerprint.hexdigest()):
        print(f"{bigread_id} is already published and unchanged; nothing to do")
        return

    publish(bigread_id, source, story, pictures)
    marker.write_text(f"{fingerprint.hexdigest()}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
