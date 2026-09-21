#!/bin/sh

# Firmware 4.1.4 has no appmgrd. Its framework exposes a native `read`
# command, which opens LAST_BOOK_READ from the reader preferences. The daily
# mission uses a stable filename and is therefore always that book after the
# first successful manual read.
exec /usr/bin/lipc-set-prop -i com.lab126.framework read 1
