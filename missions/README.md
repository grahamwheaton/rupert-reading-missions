# Mission sources

The daily job writes a mission and its artwork here. GitHub Actions builds the
MOBI the Kindle downloads. The standard ChatGPT route uses GitHub binary blobs
for pictures, without a separately billed image API key.

## What to push

```
missions/<YYYY-MM-DD>-<slug>/mission.html   required
missions/<YYYY-MM-DD>-<slug>/mission.json   optional: see below
missions/<YYYY-MM-DD>-<slug>/cover.png      illustrated 600×800 greyscale cover
missions/<YYYY-MM-DD>-<slug>/scene.png      optional picture used inside the story
```

`mission.json` carries what the Kindle dashboard shows around the story. Only
`title` and `type` matter to the book itself; the rest fill in the mission
card, and the dashboard falls back sensibly when they are missing.

| Key | Shown as |
| --- | --- |
| `title` | the mission title |
| `type` | the line under it, when there is no `subtitle` |
| `subtitle` | the line under the title |
| `blurb` | the teaser beside the illustration |
| `tags` | up to four icon-and-text rows: `{"icon": "terrain", "text": "4x4s"}` |
| `mission` | the mission number; counted from the archive when absent |

Tag icons are `terrain`, `wrench`, `book` or `star`; any other name is ignored.
Values are flattened to one line each, so a blurb may be written across several
lines in the JSON. See `missions/TEMPLATE/mission.json`.

The directory name's date prefix is the mission ID, and the newest one wins.
`missions/TEMPLATE/` has no date prefix, so it is ignored by the build.

Without `mission.json`, the title comes from the `<title>` tag and the type
defaults to `Fiction`.

## Writing for a seven-year-old

He is learning to read, so the device is set up to help: larger type, wide
even margins, loose line spacing, ragged-right text and **hyphenation off**,
so no word is ever split across two lines.

That only works if the mission does not fight it:

- **Do not set page margins, padding or indents.** The Kindle's own settings
  handle spacing, and CSS margins here make it look uneven. Style structure
  (centred headings, a rule around the fact box), not layout.
- **Avoid hyphenated words** where a simple one exists: "mountain bike trails"
  rather than "mountain-bike trails". A hyphen mid-sentence is a stumble.
- **Short sentences, one idea per line**, and paragraphs of a few lines so he
  can find his place again after looking up.
- **Plain words first.** Introduce one harder word when the story needs it, and
  let the sentence around it explain it.
- **Em dashes and semicolons** are harder than a full stop. Prefer two
  sentences.
- **Put the picture first**, before the title, so the book opens on the
  artwork rather than a page holding nothing but a heading.
- **Keep headings small** — `h1 { font-size: 1.3em }`. His reading text is
  already large, so a default heading is about twice that and fills the first
  page before the story starts.

`missions/TEMPLATE/mission.html` is a working example.

## Illustrations

Generate artwork in ChatGPT, convert it to an 8-bit greyscale PNG and upload it
through `github.create_blob` with `encoding: "base64"`. Attach the resulting
blob SHA as a binary `cover.png` or scene file in a Git tree commit, alongside
`mission.html` and `mission.json`. Do not put a large base64 image in a GitHub
text-file update. This uses ChatGPT image generation and no separate API key.

Use local relative paths for pictures inside the book:

```html
<img alt="Tom and Scout beside the bridge" src="bridge.png">
```

The builder checks every local image exists and can be decoded, tracks it for
corrected same-date publications, and Calibre packages it into the MOBI. A
missing or damaged scene fails the build. Legacy base64 data URIs in the HTML
and `cover.png.base64.partNN` cover files still work for old stories. If there
is no cover, the builder draws a simple fallback, though authored art looks
better. The final MOBI remains necessary for the stock Kindle 4 reader; the
format choice does not affect how image files reach GitHub.

## What the build produces

`tools/build-mission.py`, run by `.github/workflows/build-mission.yml`:

| File | |
| --- | --- |
| `published/today.mobi` | what the Kindle downloads |
| `published/date.txt` | the mission ID the Kindle checks |
| `published/today.sha256` | digest of `today.mobi` |
| `published/launcher.properties` | id, title, type, streak, mission, and any subtitle/blurb/tags |
| `published/archive/<id>.mobi` | every mission, kept |

Conversion uses `--mobi-file-type old --output-profile kindle`. Firmware 4.1.4
cannot open KF8, so the legacy MOBI 6 flag is not optional.

## The ordering guarantee

`date.txt` is written **last**, after the book has been built and checked for
minimum size and a `BOOKMOBI` header. If conversion fails or produces junk, the
pointer does not move and the Kindle keeps yesterday's story rather than
chasing a book that does not exist.

Re-running is a no-op when `date.txt` already matches the newest mission.
