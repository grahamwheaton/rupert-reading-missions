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
