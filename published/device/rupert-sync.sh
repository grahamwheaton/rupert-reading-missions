#!/bin/sh

BASE_URL='https://raw.githubusercontent.com/grahamwheaton/rupert-reading-missions/master/published'
RUNTIME=/usr/local/rupert
SELF="$RUNTIME/sync.sh"
STATE=/mnt/us/rupert-mission
DOCUMENT=/mnt/us/documents/RupertsMission.mobi
ARCHIVE="$STATE/archive"
ARCHIVE_KEEP=14
LOG="$STATE/sync.log"
LOG_MAX_BYTES=65536
LOCK=/var/tmp/rupert-mission-sync.lock
CURL="$RUNTIME/curl"
CA="$RUNTIME/cacert.pem"
# tmpfs, not /mnt/us: the user store disappears from Linux in USB mode, which
# used to hide a live listener's PID file and start a duplicate every 5 minutes.
WAKE_PID=/var/tmp/rupert-wake-listener.pid
# lipc-wait-event splits its comma-separated event list in place, so /proc
# shows the arguments space-separated.
WAIT_EVENT_CMD='/usr/bin/lipc-wait-event -m com.lab126.powerd outOfScreenSaver resuming '

# Run from a tmpfs copy so nothing holds $SELF open. An open (replaced) copy on
# the root filesystem stops the updater remounting it read-only.
case "$0" in
    /var/tmp/rupert-sync-run.*) rm -f "$0" ;;
    *)
        RUN=/var/tmp/rupert-sync-run.$$
        cp "$SELF" "$RUN" 2>/dev/null && exec /bin/sh "$RUN" "$@"
        ;;
esac

# In USB mode /mnt/us is unmounted; writing there would land on the root
# filesystem's empty mount point.
grep -q ' /mnt/us ' /proc/mounts || exit 0

log() {
    echo "$(date) $*" >> "$LOG"
}

cmdline() {
    tr '\0' ' ' < "/proc/$1/cmdline" 2>/dev/null
}

# Run a background check whenever the user wakes the Kindle. The normal cron
# entry remains as a fallback while the device is already awake.
if [ "$1" = "--wake-listener" ]; then
    echo $$ > "$WAKE_PID"
    /usr/bin/lipc-wait-event -m com.lab126.powerd outOfScreenSaver,resuming | while read EVENT; do
        case "$EVENT" in
            outOfScreenSaver*|resuming*)
                log 'Kindle wake received; starting mission sync'
                /bin/sh "$SELF" --scheduled >/dev/null 2>&1 &
                ;;
        esac
    done
    exit 0
fi

# Listeners run from a tmpfs copy; v16 and earlier ran $SELF directly.
is_listener() {
    case "$1" in
        "/bin/sh /var/tmp/rupert-sync-run."*" --wake-listener "|"/bin/sh $SELF --wake-listener ") return 0 ;;
    esac
    return 1
}

listener_running() {
    PID=$(cat "$WAKE_PID" 2>/dev/null)
    [ -n "$PID" ] && is_listener "$(cmdline "$PID")"
}

stop_stray_listeners() {
    for DIR in /proc/[0-9]*; do
        CMD=$(cmdline "${DIR#/proc/}")
        if is_listener "$CMD" || [ "$CMD" = "$WAIT_EVENT_CMD" ]; then
            kill "${DIR#/proc/}" 2>/dev/null
        fi
    done
}

mkdir -p "$STATE" "$ARCHIVE"
if ! listener_running; then
    stop_stray_listeners
    rm -f "$WAKE_PID"
    /bin/sh "$SELF" --wake-listener >/dev/null 2>&1 &
fi

mkdir "$LOCK" 2>/dev/null || exit 0

WIFI_RESTORE=false
cleanup() {
    [ "$WIFI_RESTORE" = true ] && /usr/bin/lipc-set-prop com.lab126.wifid enable 0 >/dev/null 2>&1
    rmdir "$LOCK" 2>/dev/null
}
trap cleanup EXIT

if [ -f "$LOG" ] && [ "$(wc -c < "$LOG")" -gt "$LOG_MAX_BYTES" ]; then
    tail -n 500 "$LOG" > "$LOG.tmp" && mv -f "$LOG.tmp" "$LOG"
fi

if [ ! -x "$CURL" ] || [ ! -f "$CA" ]; then
    log 'secure downloader is missing'
    exit 0
fi

# Only turn Wi-Fi on for the check, and put it back off afterwards if the user
# had it off. Leaving the radio on is the main battery cost of this system.
if [ "$(/usr/bin/lipc-get-prop com.lab126.wifid enable 2>/dev/null)" != 1 ]; then
    /usr/bin/lipc-set-prop com.lab126.wifid enable 1 >/dev/null 2>&1 && WIFI_RESTORE=true
fi

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

# Kindlet log snapshots for USB debugging; enable by creating $STATE/debug.
if [ -f "$STATE/debug" ]; then
    tail -1200 /var/log/messages 2>/dev/null > "$STATE/kindlet-live.log"
    grep -i -B 20 -A 40 'kindlet\|rupert\|main class\|runtimeexception\|noclass\|classnotfound\|securityexception\|exception' \
        /var/log/messages 2>/dev/null | tail -2400 > "$STATE/kindlet-errors.log"
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

# Keep the newest $ARCHIVE_KEEP missions; IDs are dates, so name order is age.
ls -1 "$ARCHIVE"/*.mobi 2>/dev/null | sort -r | awk "NR > $ARCHIVE_KEEP" | while read OLD; do
    rm -f "$OLD" "${OLD%.mobi}.properties"
done

# Prompt the framework to notice changed documents after a resume-style event.
dbus-send --system /default com.lab126.powerd.resuming int32:1 >/dev/null 2>&1 || true
exit 0
