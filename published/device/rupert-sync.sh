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
WAKE_PID="$STATE/wake-listener.pid"

log() {
    echo "$(date) $*" >> "$LOG"
}

# Run a background check whenever the user wakes the Kindle. The normal cron
# entry remains as a fallback while the device is already awake.
if [ "$1" = "--wake-listener" ]; then
    echo $$ > "$WAKE_PID"
    trap 'rm -f "$WAKE_PID"' EXIT
    /usr/bin/lipc-wait-event -m com.lab126.powerd outOfScreenSaver,resuming | while read EVENT; do
        case "$EVENT" in
            outOfScreenSaver*|resuming*)
                log 'Kindle wake received; starting mission sync'
                "$0" --scheduled >/dev/null 2>&1 &
                ;;
        esac
    done
    exit 0
fi

mkdir -p "$STATE" "$ARCHIVE"
LISTENER_RUNNING=false
if [ -f "$WAKE_PID" ]; then
    PID=$(cat "$WAKE_PID" 2>/dev/null)
    [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null && LISTENER_RUNNING=true
fi
if [ "$LISTENER_RUNNING" != true ]; then
    rm -f "$WAKE_PID"
    "$0" --wake-listener >/dev/null 2>&1 &
fi

mkdir "$LOCK" 2>/dev/null || exit 0
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

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

# Keep a bounded rolling snapshot while the first launcher is being proven.
# It makes loader failures visible over USB without requiring SSH or typing.
tail -1200 /var/log/messages 2>/dev/null > "$STATE/kindlet-live.log"
grep -i -B 20 -A 40 'kindlet\|rupert\|main class\|runtimeexception\|noclass\|classnotfound\|securityexception\|exception' \
    /var/log/messages 2>/dev/null | tail -2400 > "$STATE/kindlet-errors.log"

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
