#!/usr/bin/env python3
"""Deterministic illustrated Kindle cover when an authored image was not sent.

The title remains the only text. A supplied cover always takes precedence.
Scenes are deliberately simple greyscale drawings so GitHub Actions can build
them without an image service, credential or binary upload.
"""
import hashlib
import math
import pathlib
import random
import re

from PIL import Image, ImageDraw, ImageFont

W, H = 600, 800


def font(size):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        if pathlib.Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def tree(draw, x, y, scale, shade):
    draw.rectangle((x - scale // 10, y - scale, x + scale // 10, y), fill=shade)
    for i in range(4):
        yy = y - scale + i * scale // 5
        width = scale * (0.25 + i * 0.13)
        draw.polygon([(x, yy - scale // 5), (x - width, yy + scale // 3),
                      (x + width, yy + scale // 3)], fill=shade)


def truck(draw, x, y, scale, shade):
    draw.rectangle((x, y, x + 3 * scale, y + scale), fill=shade)
    draw.polygon([(x + 3 * scale, y + scale), (x + 3 * scale, y - scale // 2),
                  (x + 4 * scale, y - scale // 2), (x + 5 * scale, y + scale)], fill=shade)
    draw.rectangle((x + 3 * scale + 5, y - scale // 3,
                    x + 4 * scale - 4, y + scale // 3), fill=218)
    for xx in (x + scale, x + 4 * scale):
        draw.ellipse((xx - scale // 3, y + scale * 3 // 4,
                      xx + scale // 3, y + scale * 4 // 3), fill=12)


def landscape(draw, rng):
    # Broad atmospheric shapes read on a low-resolution e-ink screen.
    for row in range(H):
        shade = int(231 - row * 0.12)
        draw.line((0, row, W, row), fill=max(100, shade))
    for layer, shade in enumerate((188, 143, 103)):
        base = 360 + layer * 94
        peaks = [(0, base)]
        for x in range(0, W + 40, 40):
            peaks.append((x, base - rng.randint(10, 115 - layer * 18)))
        peaks += [(W, H), (0, H)]
        draw.polygon(peaks, fill=shade)
    for x in range(-20, W + 40, 42):
        y = rng.randint(530, 685)
        tree(draw, x, y, rng.randint(44, 99), rng.choice((35, 48, 57)))


def bridge_scene(draw, rng):
    draw.polygon([(0, 590), (600, 560), (600, 800), (0, 800)], fill=214)
    for y in range(590, 800, 13):
        for x in range(0, W, 28):
            dx = rng.randint(-9, 9)
            draw.arc((x + dx, y, x + dx + 40, y + 9), 190, 350, fill=89, width=2)
    draw.polygon([(52, 650), (530, 582), (548, 628), (52, 704)], fill=36)
    for x in range(70, 530, 32):
        yy = 653 - (x - 52) * 0.14
        draw.line((x, yy, x + 12, yy + 48), fill=199, width=3)
    for x in (92, 190, 302, 468, 528):
        yy = 687 - (x - 52) * 0.14
        draw.line((x, yy, x - 5, 760), fill=31, width=10)
    draw.polygon([(360, 613), (386, 609), (400, 654), (370, 666)], fill=212)
    truck(draw, 256, 552, 25, 24)
    tree(draw, 65, 694, 165, 19)
    truck(draw, 28, 684, 18, 34)


def ship_scene(draw, rng):
    draw.rectangle((0, 575, W, H), fill=47)
    for y in range(578, 800, 19):
        for x in range(0, W, 40):
            draw.line((x + rng.randrange(20), y, x + rng.randrange(35, 58), y),
                      fill=160, width=2)
    draw.polygon([(0, 615), (107, 465), (196, 606), (271, 638)], fill=220)
    draw.polygon([(440, 662), (520, 560), (600, 669)], fill=207)
    draw.polygon([(163, 539), (596, 536), (552, 636), (243, 630)], fill=20)
    draw.rectangle((235, 479, 538, 537), fill=230)
    draw.rectangle((296, 441, 522, 475), fill=203)
    for x in (328, 380, 432, 486):
        draw.rectangle((x, 396, x + 14, 442), fill=33)
    for y in (492, 513, 559):
        for x in range(252, 529, 18):
            draw.ellipse((x, y, x + 5, y + 4), fill=32 if y < 537 else 192)
    draw.line((380, 390, 380, 537), fill=25, width=3)


def road_scene(draw, rng):
    draw.polygon([(225, 520), (373, 520), (600, 800), (0, 800)], fill=197)
    draw.line([(300, 526), (300, 640), (300, 800)], fill=56, width=5)
    for x in (42, 112, 493, 565):
        tree(draw, x, 697, 127, 29)
    truck(draw, 208, 666, 38, 22)
    for x, y in ((165, 668), (456, 722), (81, 757)):
        draw.ellipse((x - 26, y - 12, x + 38, y + 14), fill=78)


def title_art(draw, title):
    title = re.sub(r"\s+", " ", title.upper()).strip()[:80] or "READING MISSION"
    words = title.split()
    for size in range(72, 34, -2):
        face = font(size)
        lines, line = [], ""
        for word in words:
            attempt = (line + " " + word).strip()
            if line and draw.textbbox((0, 0), attempt, font=face)[2] > 548:
                lines.append(line)
                line = word
            else:
                line = attempt
        lines.append(line)
        if len(lines) <= 3 and len(lines) * (size + 8) <= 235:
            break
    height = len(lines) * (size + 8) + 35
    draw.rectangle((10, 25, 590, 25 + height), fill=24)
    for index, line in enumerate(lines):
        width = draw.textbbox((0, 0), line, font=face)[2]
        draw.text(((W - width) / 2, 40 + index * (size + 8)), line,
                  font=face, fill=244)


def create_cover(title, story, destination):
    image = Image.new("L", (W, H), 235)
    draw = ImageDraw.Draw(image)
    seed = int(hashlib.sha256((title + story).encode("utf-8")).hexdigest()[:12], 16)
    rng = random.Random(seed)
    landscape(draw, rng)
    text = (title + " " + story).lower()
    if any(word in text for word in ("titanic", "ship", "iceberg", "ocean")):
        ship_scene(draw, rng)
    elif any(word in text for word in ("bridge", "river crossing", "winch")):
        bridge_scene(draw, rng)
    else:
        road_scene(draw, rng)
    title_art(draw, title)
    # Keep the same 600x800 8-bit greyscale format as authored covers.
    image.save(destination, format="PNG", optimize=True)
