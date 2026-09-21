#!/bin/sh

LOG=/mnt/us/rupert-mission/lipc-probe.log

{
    echo "=== Rupert reader service probe: $(date) ==="
    echo '=== LIPC services and properties ==='
    /usr/bin/lipc-probe -a -v 2>&1
    echo '=== D-Bus registered names ==='
    /usr/bin/dbus-send --system --print-reply --dest=org.freedesktop.DBus \
        / org.freedesktop.DBus.ListNames 2>&1
} > "$LOG"

exit 0
