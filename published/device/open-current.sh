#!/bin/sh

# Opens today's mission in KOReader (kindle-legacy build, installed by hand at
# /mnt/us/koreader). Firmware 4.1.4's own framework cannot open a document by
# path: `lipc-set-prop com.lab126.framework read 1` is accepted but returns to
# Home. KOReader takes the file as an argument instead.
#
# BusyBox on the K4 has no nohup; a backgrounded subshell detaches KOReader
# from the Kindlet, which exits after starting this script.

MISSION=/mnt/us/documents/RupertsMission.mobi
KOREADER=/mnt/us/koreader/koreader.sh
LOG=/mnt/us/rupert-mission/open-current.log

echo "$(date) opening $MISSION" >> "$LOG"

if [ ! -f "$KOREADER" ]; then
    echo "$(date) KOReader missing; falling back to framework read" >> "$LOG"
    exec /usr/bin/lipc-set-prop -i com.lab126.framework read 1
fi

if pidof reader.lua >/dev/null 2>&1; then
    echo "$(date) KOReader already running" >> "$LOG"
    exit 0
fi

( "$KOREADER" --kual "$MISSION" >> "$LOG" 2>&1 & )
exit 0
