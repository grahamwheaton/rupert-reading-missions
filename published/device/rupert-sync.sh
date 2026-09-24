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

# Report finished missions while the radio is already on. Does nothing unless
# a token and repository have been configured.
[ -x "$RUNTIME/report.sh" ] && "$RUNTIME/report.sh" >/dev/null 2>&1 || true

# Kindlet log snapshots for USB debugging; enable by creating $STATE/debug.
if [ -f "$STATE/debug" ]; then
    tail -1200 /var/log/messages 2>/dev/null > "$STATE/kindlet-live.log"
    grep -i -B 20 -A 40 'kindlet\|rupert\|main class\|runtimeexception\|noclass\|classnotfound\|securityexception\|exception' \
        /var/log/messages 2>/dev/null | tail -2400 > "$STATE/kindlet-errors.log"
fi

# wifid reports CONNECTED from the previous association before the radio is
# usable again, so the first request after switching Wi-Fi on often fails.
# Retry rather than waiting for the next scheduled run.
fetch() {
    TRY=1
    while :; do
        "$CURL" --proto '=https' --tlsv1.2 --fail --silent --show-error --location \
            --connect-timeout 20 --max-time 90 --cacert "$CA" -o "$1" "$2" && return 0
        [ "$TRY" -ge 3 ] && return 1
        TRY=$((TRY + 1))
        sleep 8
    done
}

STAMP="$STATE/date.part"
DIGEST_PART="$STATE/digest.part"
BOOK="$STATE/today.mobi.part"
META="$STATE/launcher.properties.part"
rm -f "$STAMP" "$DIGEST_PART" "$BOOK" "$META"

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

# The ID alone would miss a corrected story: fixing a mission republishes it
# under the same date. The published digest changes whenever the book does.
if fetch "$DIGEST_PART" "$BASE_URL/today.sha256" >> "$LOG" 2>&1; then
    REMOTE_DIGEST=$(tr -d '\r\n ' < "$DIGEST_PART")
fi
rm -f "$DIGEST_PART"

# The weekly Big Read: story and pictures in one tar, checked the same way as
# a mission. Failing here must not disturb today's mission, which is already
# installed by this point.
BIGREAD_ID_PART="$STATE/bigread-id.part"
BIGREAD_DIGEST_PART="$STATE/bigread-digest.part"
BIGREAD_TAR="$STATE/bigread.tar.part"
rm -f "$BIGREAD_ID_PART" "$BIGREAD_DIGEST_PART" "$BIGREAD_TAR"
if fetch "$BIGREAD_ID_PART" "$BASE_URL/bigread.txt" >> "$LOG" 2>&1; then
    BIGREAD_ID=$(tr -d '
 ' < "$BIGREAD_ID_PART")
    fetch "$BIGREAD_DIGEST_PART" "$BASE_URL/bigread.sha256" >> "$LOG" 2>&1         && BIGREAD_DIGEST=$(tr -d '
 ' < "$BIGREAD_DIGEST_PART")

    if [ -n "$BIGREAD_ID" ] && [ -n "$BIGREAD_DIGEST" ]         && { [ "$(cat "$STATE/bigread-id" 2>/dev/null)" != "$BIGREAD_ID" ]             || [ "$(cat "$STATE/bigread-digest" 2>/dev/null)" != "$BIGREAD_DIGEST" ]             || [ ! -f "$STATE/bigread/story.json" ]; }
    then
        if fetch "$BIGREAD_TAR" "$BASE_URL/bigread.tar" >> "$LOG" 2>&1; then
            LOCAL_DIGEST=$(/usr/bin/openssl dgst -sha256 "$BIGREAD_TAR" 2>/dev/null | awk '{print $NF}')
            if [ "$LOCAL_DIGEST" = "$BIGREAD_DIGEST" ]; then
                rm -rf "$STATE/bigread.new"
                mkdir -p "$STATE/bigread.new"
                if tar -xf "$BIGREAD_TAR" -C "$STATE/bigread.new" 2>> "$LOG"                     && [ -f "$STATE/bigread.new/story.json" ]
                then
                    rm -rf "$STATE/bigread.old"
                    [ -d "$STATE/bigread" ] && mv "$STATE/bigread" "$STATE/bigread.old"
                    mv "$STATE/bigread.new" "$STATE/bigread"
                    rm -rf "$STATE/bigread.old"
                    echo "$BIGREAD_ID" > "$STATE/bigread-id"
                    echo "$BIGREAD_DIGEST" > "$STATE/bigread-digest"
                    log "installed Big Read $BIGREAD_ID"
                else
                    log 'Big Read rejected: the archive would not unpack'
                    rm -rf "$STATE/bigread.new"
                fi
            else
                log 'Big Read rejected: digest did not match the published one'
            fi
        else
            log 'Big Read download failed'
        fi
    fi
fi
rm -f "$BIGREAD_ID_PART" "$BIGREAD_DIGEST_PART" "$BIGREAD_TAR"

# The unlock store changes independently of the daily book. Its public
# catalog contains only names, prices and preprocessed thumbnail images.
# Never fetch the private ActionNotes repository from the Kindle.
UNLOCK_URL="$BASE_URL/unlocks"
UNLOCK_NEW="$STATE/unlock-catalog.new"
UNLOCK_DIR="$STATE/unlock-catalog"
rm -rf "$UNLOCK_NEW"
mkdir -p "$UNLOCK_NEW/images"
if fetch "$UNLOCK_NEW/catalog.sha256" "$UNLOCK_URL/catalog.sha256" >> "$LOG" 2>&1 \
    && fetch "$UNLOCK_NEW/catalog.tsv" "$UNLOCK_URL/catalog.tsv" >> "$LOG" 2>&1
then
    EXPECTED=$(tr -d '\r\n ' < "$UNLOCK_NEW/catalog.sha256")
    ACTUAL=$(/usr/bin/openssl dgst -sha256 "$UNLOCK_NEW/catalog.tsv" 2>/dev/null | awk '{print $NF}')
    VALID=true
    [ "$EXPECTED" = "$ACTUAL" ] || VALID=false
    TAB=$(printf '\t')
    while IFS="$TAB" read -r ITEM_ID PENCE POINTS TITLE IMAGE_SHA; do
        [ -z "$ITEM_ID" ] && continue
        case "$ITEM_ID" in *[!a-z0-9-]*|'') VALID=false; break ;; esac
        case "$PENCE:$POINTS" in *[!0-9:]*|'') VALID=false; break ;; esac
        case "$IMAGE_SHA" in *[!a-f0-9]*|'') VALID=false; break ;; esac
        [ "${#IMAGE_SHA}" -eq 64 ] || { VALID=false; break; }
        [ -n "$TITLE" ] || { VALID=false; break; }
        [ "$VALID" = true ] || break
        if ! fetch "$UNLOCK_NEW/images/$ITEM_ID.png" "$UNLOCK_URL/images/$ITEM_ID.png" >> "$LOG" 2>&1; then
            VALID=false
            break
        fi
        IMAGE_DIGEST=$(/usr/bin/openssl dgst -sha256 "$UNLOCK_NEW/images/$ITEM_ID.png" 2>/dev/null | awk '{print $NF}')
        [ "$IMAGE_SHA" = "$IMAGE_DIGEST" ] || { VALID=false; break; }
    done < "$UNLOCK_NEW/catalog.tsv"
    if [ "$VALID" = true ]; then
        rm -rf "$STATE/unlock-catalog.old"
        [ -d "$UNLOCK_DIR" ] && mv "$UNLOCK_DIR" "$STATE/unlock-catalog.old"
        mv "$UNLOCK_NEW" "$UNLOCK_DIR"
        rm -rf "$STATE/unlock-catalog.old"
        log 'installed unlock catalog'
    else
        log 'unlock catalog rejected: digest or contents invalid'
    fi
fi
rm -rf "$UNLOCK_NEW"

if [ "$(cat "$STATE/last-remote-id" 2>/dev/null)" = "$REMOTE_ID" ] \
    && [ "$(cat "$STATE/last-remote-digest" 2>/dev/null)" = "$REMOTE_DIGEST" ] \
    && [ -f "$DOCUMENT" ] && [ -f "$STATE/launcher.properties" ]; then
    exit 0
fi

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

# GitHub can briefly serve a new digest beside the old book (or the reverse).
# A mismatch means we caught it mid-publish: leave everything alone and let the
# next run pick it up.
if [ -n "$REMOTE_DIGEST" ]; then
    LOCAL_DIGEST=$(/usr/bin/openssl dgst -sha256 "$BOOK" 2>/dev/null | awk '{print $NF}')
    if [ "$LOCAL_DIGEST" != "$REMOTE_DIGEST" ]; then
        log 'mission rejected: digest did not match the published one'
        rm -f "$BOOK" "$META"
        exit 0
    fi
fi

OLD_ID=$(cat "$STATE/last-remote-id" 2>/dev/null)
if [ -n "$OLD_ID" ] && [ -f "$DOCUMENT" ]; then
    cp "$DOCUMENT" "$ARCHIVE/$OLD_ID.mobi"
    [ -f "$STATE/launcher.properties" ] && cp "$STATE/launcher.properties" "$ARCHIVE/$OLD_ID.properties"
fi

mv -f "$BOOK" "$DOCUMENT"

# The mission keeps one filename, so the reader would carry the previous
# story's position, font and margins into today's. Start each one clean.
rm -rf "${DOCUMENT%.mobi}.sdr"
mv -f "$META" "$STATE/launcher.properties"
echo "$REMOTE_ID" > "$STATE/last-remote-id"
echo "$REMOTE_DIGEST" > "$STATE/last-remote-digest"
log "installed mission $REMOTE_ID ($SIZE bytes)"

# Keep the newest $ARCHIVE_KEEP missions; IDs are dates, so name order is age.
ls -1 "$ARCHIVE"/*.mobi 2>/dev/null | sort -r | awk "NR > $ARCHIVE_KEEP" | while read OLD; do
    rm -f "$OLD" "${OLD%.mobi}.properties"
done

# Prompt the framework to notice changed documents after a resume-style event.
dbus-send --system /default com.lab126.powerd.resuming int32:1 >/dev/null 2>&1 || true
exit 0
