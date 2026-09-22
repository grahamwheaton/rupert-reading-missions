# Mission sources

The daily job writes a mission here as **text only**. GitHub Actions builds the
MOBI the Kindle downloads. Nothing that writes to this repository needs to be
able to push binary files.

## What to push

```
missions/<YYYY-MM-DD>-<slug>/mission.html   required
missions/<YYYY-MM-DD>-<slug>/mission.json   optional: see below
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
- **Keep headings small** — `h1 { font-size: 1.3em }`. His reading text is
  already large, so a default heading is about twice that and fills the first
  page before the story starts.

`missions/TEMPLATE/mission.html` is a working example.

## Illustrations

Inline them as base64 `data:` URIs:

```html
<img alt="..." src="data:image/png;base64,iVBORw0KGgo...">
```

Calibre embeds them as normal images during conversion. Inline `<svg>` also
works but rasterises less predictably, so prefer base64. Either way the source
stays UTF-8 text.

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
