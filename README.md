# Daily Reading Mission delivery

This repository is an automated delivery endpoint for a legacy Kindle.

`published/date.txt` identifies the publication date and
`published/today.mobi` is the current reading mission. Older missions and
device configuration are not published here.


## Daily cover rule

An authored cover uses either `cover.png.base64` or numbered
`cover.png.base64.part01`, `part02`, etc.: a complete PNG encoded
as base64 text, wrapped at no more than 76 characters per line. Use
`python3 tools/encode-cover.py cover.png missions/YYYY-MM-DD-slug` to make
small parts that the GitHub text connector can upload individually. Commit
the whole numbered set together; a missing or corrupt part prevents
publication. The builder verifies the encoding, PNG checksums, 600×800
dimensions, 8-bit greyscale format, and the image record in the converted
MOBI. If no cover parts exist, it draws a story-aware illustrated cover with
the title as its only text and still publishes the book. Adding approved cover
parts later republishes the same day's book with its new image.

Make the cover a proper illustrated scene with bold, readable line art and
strong contrast for e-ink. The mission title is part of the artwork and is
**the only text on the cover**: no fiction/fact badge, tagline, series branding,
sign with words, or other copy. This visual rule requires editorial review;
the builder can verify file format, not the words in an authored image. The
automatic fallback is designed to keep daily delivery working when an image
cannot be uploaded; use the authored artwork when available.
