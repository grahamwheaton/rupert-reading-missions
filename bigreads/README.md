# Big Reads

A **Big Read** is the weekly long story, and unlike a daily mission it is
interactive: every page ends with two choices, and Rupert picks one with the
page-turn button on the left or right of the Kindle. The story then continues
down that branch.

He is seven and learning to read. Everything below exists so a page never
looks like too much.

## What to push

```
bigreads/<YYYY-MM-DD>-<slug>/story.json           required
bigreads/<YYYY-MM-DD>-<slug>/cover.png.base64     pictures, as base64 text
```

**Push pictures as base64 text, not as binary files.** The job that writes
stories can push UTF-8 reliably and binary unreliably: the first real Big Read
arrived with a cover whose header was fine but whose image data was cut off
half way. Write `cover.png.base64` containing the base64 of the PNG, and the
build decodes it. `story.json` still refers to the picture by its real name,
`cover.png`. A genuine binary file still works if you can push one.

**Wrap the base64 at 76 characters per line.** One enormous line loses
characters in transit: the second attempt at a cover arrived one byte short of
a complete PNG, having lost three characters somewhere in a 4,167-character
line. The build checks the length and says so when that happens.

Keep pictures small and they are less likely to be mangled at all. Bold line
art at one bit per pixel is about 3 KB for a full 600x800 cover, which is both
the right look for e-ink and a short enough file to survive the trip.

The date prefix is the Big Read's ID, and the newest one wins, exactly as
missions work. GitHub Actions validates the story, packs it with its pictures
and publishes it; the Kindle downloads it on its next check.

**A story that breaks a rule below is not published.** The build fails and says
why, and Rupert keeps last week's story rather than getting a broken one.

## story.json

```json
{
  "title": "The Cave of Echoes",
  "subtitle": "A caving adventure with Tom",
  "cover": "cover.png",
  "start": "cave-mouth",
  "nodes": {
    "cave-mouth": {
      "text": "Tom stopped at the mouth of the cave. Cold air came out of it, and somewhere inside, water was dripping.\n\nTwo tunnels went into the dark.",
      "image": "cave-mouth.png",
      "choices": [
        { "text": "Take the low tunnel", "next": "low-tunnel" },
        { "text": "Take the tall tunnel", "next": "tall-tunnel" }
      ]
    },
    "low-tunnel": {
      "text": "The low tunnel meant crawling...",
      "choices": [
        { "text": "Keep crawling", "next": "the-river" },
        { "text": "Go back", "next": "cave-mouth" }
      ]
    },
    "the-river": {
      "text": "Tom had found the underground river...",
      "image": "river.png",
      "ending": "You found the lost river!"
    }
  }
}
```

| Key | |
| --- | --- |
| `title` | shown on the dashboard tile and at the top of each page |
| `subtitle` | one line under the title |
| `cover` | the picture for the tile and the first screen |
| `start` | the ID of the first node |
| `nodes` | every page of the story, keyed by ID |

A node has `text`, optionally an `image`, and then **either** exactly two
`choices` **or** an `ending`. `ending` is the line he sees when he finishes,
such as "You found the lost river!".

Node IDs are lowercase letters, numbers and hyphens: `cave-mouth`, `the-river`.
Name them after what happens, not `node-17`.

## The rules the build enforces

**Page length.** The Kindle shows about twenty lines at his reading size, and
the two choices take the bottom of the screen.

| | Words per page |
| --- | --- |
| A page with a picture | 20–70 |
| A page without one | 25–110 |

One or two short paragraphs. Separate paragraphs with a blank line (`\n\n`).

**Choices.** Exactly two, and at most 40 characters each so they fit on one
line. Make them a real decision — two ways to go, two things to try — not
"carry on" versus "stop". He cannot go back, so neither choice may be a dead
end that simply ends the story early.

**Shape.** Between 20 and 60 nodes. Every node must be reachable from `start`,
and from every node it must be possible to reach an ending, so no branch can
trap him in a loop. At least three different endings, so his choices matter.
Branches may rejoin: two tunnels can arrive at the same cavern, which is how a
story stays this size.

**Pictures.** The cover is required. Then a picture roughly every four to six
pages, and one at each ending. Not every page: the whole story travels over
Wi-Fi to a fifteen-year-old Kindle.

- **8-bit greyscale PNG**, not 1-bit black and white. The screen shows sixteen
  shades of grey; pure black and white throws most of that away and makes a
  drawing look blotchy. Quantise to sixteen levels if you like, but save it as
  8-bit.
- **Draw the picture. Do not construct it from shapes in code.** A house made
  of a triangle and a rectangle is a diagram, not an illustration, and it shows
  next to a real drawing. If a picture comes out under a couple of kilobytes,
  it is almost certainly shapes rather than art.
- PNG or JPEG, at most 600 wide and 500 tall.
- The cover may be 600x800.
- The whole folder must stay under 4 MB.
- The build decodes every picture rather than trusting its header, so a
  truncated or corrupt one fails the build with the reason.
- Draw for e-ink: bold line art, strong contrast, no gradients or fine
  texture. The screen shows sixteen greys and no colour. The full guidance is
  in `assets/README.md` in the device repository.

**Writing.** The same rules as a daily mission, which matter more here because
the story is longer:

- Short sentences, one idea at a time.
- Plain words first; introduce one harder word when the story needs it and let
  the sentence explain it.
- No hyphenated compounds where a simple word exists: "mountain bike trail",
  not "mountain-bike trail".
- Full stops rather than em dashes and semicolons.
- Speech on its own line, so he can hear who is talking.
- Real facts are welcome, woven in rather than lectured.

## Checking before you push

```bash
python3 tools/build-bigread.py --check bigreads/2026-09-28-the-cave-of-echoes
```

It reports every problem at once: overlong pages, choices leading nowhere,
unreachable nodes, branches with no ending, oversized pictures. `--map` prints
the story's shape so you can see how the branches run and where the endings
are.

## What the build produces

| File | |
| --- | --- |
| `published/bigread.tar` | the story and its pictures, in one file |
| `published/bigread.sha256` | digest the Kindle checks after downloading |
| `published/bigread.txt` | the ID the Kindle compares against its copy |

`bigread.txt` is written last, after everything else exists, so the Kindle can
never be pointed at a story that is still half-published.
