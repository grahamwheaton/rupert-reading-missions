#!/bin/sh

BASE_URL='https://raw.githubusercontent.com/grahamwheaton/rupert-reading-missions/master/published'
RUNTIME=/usr/local/rupert
STATE=/mnt/us/rupert-mission
DOCUMENT=/mnt/us/documents/RupertsMission.mobi
ARCHIVE="$STATE/archive"
LOG="$STATE/sync.log"
LOCK=/tmp/rupert-mission-sync.lock
CURL="$RUNTIME/curl"
CA="$RUNTIME/cacert.pem"

mkdir "$LOCK" 2>/dev/null || exit 0
trap 'rmdir "$LOCK" 2>/dev/null' EXIT
mkdir -p "$STATE" "$ARCHIVE"

log() {
    echo "$(date) $*" >> "$LOG"
}

if [ ! -x "$CURL" ] || [ ! -f "$CA" ]; then
    log 'secure downloader is missing'
    exit 0
fi

/usr/bin/lipc-set-prop com.lab126.wifid enable 1 >/dev/null 2>&1 || true

WAIT=0
while [ "$WAIT" -lt 60 ]; do
    WIFI_STATE=$(/usr/bin/lipc-get-prop com.lab126.wifid cmState 2>/dev/null)
    echo "$WIFI_STATE" | grep -q CONNECTED && break
    sleep 5
    WAIT=$((WAIT + 5))
done

echo "$WIFI_STATE" | grep -q CONNECTED || {
    log 'Wi-Fi was not connected'
    exit 0
}

# Check the separately signed, allowlisted application update channel.
[ -x "$RUNTIME/device-update.sh" ] && "$RUNTIME/device-update.sh" >/dev/null 2>&1 || true

# One-time, bounded framework diagnostics for the initial Kindlet launch test.
if [ ! -f "$STATE/kindlet-log-captured" ]; then
    {
        echo '=== /var/log inventory ==='
        find /var/log -maxdepth 2 -type f -print 2>/dev/null
        echo '=== messages tail ==='
        tail -300 /var/log/messages 2>/dev/null
    } > "$STATE/kindlet-framework.log" 2>&1
    date > "$STATE/kindlet-log-captured"
fi

fetch() {
    "$CURL" --proto '=https' --tlsv1.2 --fail --silent --show-error --location \
        --connect-timeout 20 --max-time 90 --cacert "$CA" -o "$1" "$2"
}

STAMP="$STATE/date.part"
BOOK="$STATE/today.mobi.part"
META="$STATE/launcher.properties.part"
rm -f "$STAMP" "$BOOK" "$META"

if ! fetch "$STAMP" "$BASE_URL/date.txt" >> "$LOG" 2>&1; then
    log 'mission ID download failed'
    rm -f "$STAMP"
    exit 0
fi

REMOTE_ID=$(tr -d '\r\n ' < "$STAMP")
rm -f "$STAMP"
[ -n "$REMOTE_ID" ] || {
    log 'empty mission ID rejected'
    exit 0
}

[ "$(cat "$STATE/last-remote-id" 2>/dev/null)" = "$REMOTE_ID" ] \
    && [ -f "$DOCUMENT" ] && [ -f "$STATE/launcher.properties" ] && exit 0

if ! fetch "$BOOK" "$BASE_URL/today.mobi" >> "$LOG" 2>&1; then
    log 'mission download failed'
    rm -f "$BOOK"
    exit 0
fi

if ! fetch "$META" "$BASE_URL/launcher.properties" >> "$LOG" 2>&1; then
    log 'launcher metadata download failed'
    rm -f "$BOOK" "$META"
    exit 0
fi

SIZE=$(wc -c < "$BOOK")
if [ "$SIZE" -lt 1024 ]; then
    log "mission rejected: only $SIZE bytes"
    rm -f "$BOOK"
    exit 0
fi

OLD_ID=$(cat "$STATE/last-remote-id" 2>/dev/null)
if [ -n "$OLD_ID" ] && [ -f "$DOCUMENT" ]; then
    cp "$DOCUMENT" "$ARCHIVE/$OLD_ID.mobi"
    [ -f "$STATE/launcher.properties" ] && cp "$STATE/launcher.properties" "$ARCHIVE/$OLD_ID.properties"
fi

mv -f "$BOOK" "$DOCUMENT"
mv -f "$META" "$STATE/launcher.properties"
echo "$REMOTE_ID" > "$STATE/last-remote-id"
log "installed mission $REMOTE_ID ($SIZE bytes)"

# Prompt the framework to notice changed documents after a resume-style event.
dbus-send --system /default com.lab126.powerd.resuming int32:1 >/dev/null 2>&1 || true
exit 0
