# Daily Reading Mission delivery

This repository is an automated delivery endpoint for a legacy Kindle.

`published/date.txt` identifies the publication date and
`published/today.mobi` is the current reading mission. Older missions and
device configuration are not published here.


## Daily cover rule

Each dated mission directory must include `cover.png.base64`: a complete PNG
encoded as base64 text, wrapped at no more than 76 characters per line. The
builder verifies the encoding, PNG checksums, 600×800 dimensions, 8-bit
greyscale format, and the image record in the converted MOBI. It refuses to
publish when any of these checks fail.

Make the cover a proper illustrated scene with bold, readable line art and
strong contrast for e-ink. The mission title is part of the artwork and is
**the only text on the cover**: no fiction/fact badge, tagline, series branding,
sign with words, or other copy. This visual rule requires editorial review;
the builder can verify file format and presence, not the words in an image.
