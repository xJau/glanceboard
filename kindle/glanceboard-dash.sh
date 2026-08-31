#!/bin/sh
# Copyright 2026 Glanceboard Kindle contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Glanceboard dash loop for a jailbroken Kindle.
#
#   wake -> wifi on -> ask the server what is current -> download only if it
#   changed -> draw with eips -> wifi off -> suspend to RAM until the next slot
#
# POSIX sh for BusyBox. No bashisms, no arrays, no `local`.
#
# The device never decides *when* the next board is due: it subtracts two epoch
# values the server sends it. A Kindle clock is UTC, drifts while suspended and
# knows nothing about daylight saving, so it is not trusted for scheduling.

set -u

CONF_FILE="${GLANCEBOARD_CONF:-/mnt/us/glanceboard/glanceboard.conf}"

# ─── Defaults, overridable in the conf file ──────────────────────
BASE_URL=""
DISPLAY_TOKEN=""
CF_ACCESS_CLIENT_ID=""
CF_ACCESS_CLIENT_SECRET=""
CA_BUNDLE=""
ALLOW_INSECURE_TLS=0
STATE_DIR="/mnt/us/glanceboard/state"
LOG_FILE="/mnt/us/glanceboard/glanceboard.log"
WAKE_GRACE=120          # seconds after a slot before waking, so the PNG is ready
MIN_SLEEP=300           # never suspend for less than this
MAX_SLEEP=21600         # nor longer, so a stuck server still gets retried
RETRY_SLEEP=600         # after a failed cycle
WIFI_TIMEOUT=45         # seconds to wait for an address
FULL_REFRESH_EVERY=6    # full panel flashes to clear e-ink ghosting
MANAGE_WIFI=1           # turn the radio off between refreshes
FAILS_BEFORE_NOTICE=3   # consecutive failures before the panel says so
DEDICATED="${DEDICATED:-0}"  # 1: stop the reader UI, but only once a board is up
UI_STOP_TIMEOUT=25      # seconds to wait for the reader UI to actually exit
UI_SETTLE=4             # seconds to let the panel settle afterwards
RADIO_RETRY_SLEEP=5     # pause after nudging the radio, before retrying
SUSPEND_GRACE=10        # seconds before suspending, so the loop can be killed
# Where the wake alarm lives. The Kindle's i.MX interface comes first: the
# generic /sys/class/rtc path does not exist on this hardware, and writing to a
# path that is not there fails silently.
RTC_PATHS="/sys/devices/platform/mxc_rtc.0/wakeup_enable /sys/class/rtc/rtc1/wakealarm /sys/class/rtc/rtc0/wakealarm"
SYS_POWER_STATE=/sys/power/state
# Env-overridable: dedicated mode passes FRONT_LIGHT=0, and the conf file,
# sourced below, still has the last word.
FRONT_LIGHT="${FRONT_LIGHT:--1}"   # 0 turns the front light off; -1 leaves it alone
LOG_MAX_BYTES=131072

# shellcheck source=/dev/null
[ -f "$CONF_FILE" ] && . "$CONF_FILE"

IMAGE_FILE="$STATE_DIR/board.png"
HASH_FILE="$STATE_DIR/last_hash"
COUNTER_FILE="$STATE_DIR/refresh_count"

mkdir -p "$STATE_DIR" 2>/dev/null

log() {
    printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S')" "$*" >> "$LOG_FILE" 2>/dev/null
    # Only echo when someone is watching. Under the KUAL launcher stdout is
    # redirected to this same file, and every line would land in it twice —
    # halving what fits on the "Mostra log" screen, which is the only way to
    # read it on a device with no shell.
    [ -t 1 ] && printf '%s\n' "$*"
    return 0
}

rotate_log() {
    [ -f "$LOG_FILE" ] || return 0
    size=$(wc -c < "$LOG_FILE" 2>/dev/null || echo 0)
    [ "$size" -gt "$LOG_MAX_BYTES" ] && mv "$LOG_FILE" "$LOG_FILE.1" 2>/dev/null
    return 0
}

die_if_unconfigured() {
    if [ -z "$BASE_URL" ] || [ -z "$DISPLAY_TOKEN" ]; then
        log "FATAL: BASE_URL and DISPLAY_TOKEN must be set in $CONF_FILE"
        exit 2
    fi
}

# ─── Wi-Fi ───────────────────────────────────────────────────────

wifi_on() {
    [ "$MANAGE_WIFI" = "1" ] || return 0
    lipc-set-prop com.lab126.cmd wirelessEnable 1 2>/dev/null
    waited=0
    while [ "$waited" -lt "$WIFI_TIMEOUT" ]; do
        if lipc-get-prop com.lab126.wifid cmState 2>/dev/null | grep -q CONNECTED; then
            return 0
        fi
        sleep 3
        waited=$((waited + 3))
    done
    log "WARN: wifi did not report CONNECTED after ${WIFI_TIMEOUT}s; trying anyway"
    return 0
}

wifi_off() {
    [ "$MANAGE_WIFI" = "1" ] || return 0
    lipc-set-prop com.lab126.cmd wirelessEnable 0 2>/dev/null
}

# ─── HTTP ────────────────────────────────────────────────────────
# curl is preferred. BusyBox wget is the fallback; if it cannot set headers,
# the token goes in the query string — the server accepts that for this reason.

http_get() {
    # http_get <path> <output-file|-> ; prints body to stdout when output is '-'
    url="${BASE_URL}$1"
    out="$2"

    if command -v curl >/dev/null 2>&1; then
        set -- -sS --fail --max-time 60 \
            -H "Authorization: Bearer ${DISPLAY_TOKEN}"
        [ -n "$CF_ACCESS_CLIENT_ID" ] && set -- "$@" -H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}"
        [ -n "$CF_ACCESS_CLIENT_SECRET" ] && set -- "$@" -H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}"
        [ -n "$CA_BUNDLE" ] && set -- "$@" --cacert "$CA_BUNDLE"
        [ "$ALLOW_INSECURE_TLS" = "1" ] && set -- "$@" --insecure
        if [ "$out" = "-" ]; then
            curl "$@" "$url"
        else
            curl "$@" -o "$out" "$url"
        fi
        return $?
    fi

    if wget --help 2>&1 | grep -q -- '--header'; then
        set -- --header="Authorization: Bearer ${DISPLAY_TOKEN}"
        [ -n "$CF_ACCESS_CLIENT_ID" ] && set -- "$@" --header="CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}"
        [ -n "$CF_ACCESS_CLIENT_SECRET" ] && set -- "$@" --header="CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}"
        if [ "$out" = "-" ]; then
            wget "$@" -q -O - "$url"
        else
            wget "$@" -q -O "$out" "$url"
        fi
        return $?
    fi

    # Last resort: no header support at all.
    if [ -n "$CF_ACCESS_CLIENT_ID" ]; then
        log "ERROR: this wget cannot send headers, and Cloudflare Access needs them"
        return 1
    fi
    separator="?"
    case "$1" in *\?*) separator="&" ;; esac
    if [ "$out" = "-" ]; then
        wget -q -O - "${url}${separator}token=${DISPLAY_TOKEN}"
    else
        wget -q -O "$out" "${url}${separator}token=${DISPLAY_TOKEN}"
    fi
}

json_field() {
    # json_field <json> <key> — flat objects only, which is all /display/check returns
    printf '%s' "$1" | sed -n "s/.*\"$2\"[[:space:]]*:[[:space:]]*\"\{0,1\}\([^,\"}]*\)\"\{0,1\}.*/\1/p" | head -n 1
}

# ─── Display ─────────────────────────────────────────────────────

set_front_light() {
    # An e-ink board needs no backlight, and in dedicated mode nothing else
    # will ever turn it off.
    [ "$FRONT_LIGHT" -ge 0 ] 2>/dev/null || return 0
    lipc-set-prop com.lab126.powerd flIntensity "$FRONT_LIGHT" 2>/dev/null
    return 0
}

enter_dedicated_mode() {
    # Stop the reader UI — from here, and only once a board is on the panel.
    #
    # Stopping it from a KUAL menu script killed the script itself, so the loop
    # never started and the device was left blank. And doing it before the first
    # fetch took the reader away from a device that then had nothing to show.
    #
    # powerd is left running. It paints a sleep screen, which is dealt with by
    # drawing the board again immediately before suspending rather than by
    # killing the service that owns the front light and the wake path.
    [ "$DEDICATED" = "1" ] || return 0
    log "entering dedicated mode"
    set_front_light
    stop_reader_ui

    # The framework repaints on its way out. The last thing to touch the panel
    # has to be us, so the board is drawn again once it is gone — twice, a few
    # seconds apart, in case a late repaint arrives after the process has died.
    FORCE_DRAW=1
    draw
    sleep "$UI_SETTLE"
    FORCE_DRAW=1
    draw
    FORCE_DRAW=0
    DEDICATED=done

    # The radio switch belongs to the framework (com.lab126.cmd). With it gone
    # the calls go nowhere, and the loop would spend forty-five seconds a cycle
    # waiting for a CONNECTED that cannot arrive.
    if [ "$MANAGE_WIFI" = "1" ]; then
        log "dedicated mode: leaving the radio on, the framework owned that switch"
        MANAGE_WIFI=0
    fi
    return 0
}

show_failure_notice() {
    # Overlay, never clear.
    #
    # This used to wipe the panel and print the tail of the log on it. After
    # half an hour of failed cycles the board was replaced by a white page with
    # truncated text — losing the one useful thing on the screen in order to
    # report that nothing new had arrived. A stale board with a line of
    # explanation across the top is strictly better: the appointments are still
    # readable, and the reason is right there.
    reason=$(grep -E "ERROR|WARN" "$LOG_FILE" 2>/dev/null | tail -n 1 | cut -c1-64)
    eips 0 0 "Glanceboard: aggiornamento non riuscito $(date '+%H:%M')" 2>/dev/null
    eips 0 1 "$reason" 2>/dev/null
    return 0
}

is_png() {
    # A server behind Cloudflare Access answers a bad request with an HTML login
    # page, and 200 OK. Checking the magic bytes is what keeps that off the
    # panel.
    [ -s "$1" ] || return 1
    head -c 4 "$1" 2>/dev/null | grep -q 'PNG'
}

draw() {
    count=$(cat "$COUNTER_FILE" 2>/dev/null)
    # A truncated or corrupt counter must not break the arithmetic below.
    case "$count" in
        ''|*[!0-9]*) count=0 ;;
    esac
    count=$((count + 1))

    # `eips -f -g` does a full refresh and the draw in one command. Clearing
    # first with `eips -c` and drawing after leaves the panel white in between,
    # and if the draw then fails — or anything repaints during the gap — white
    # is what stays. That gap is what a "frame for one second, then white"
    # looks like.
    if [ "$count" -ge "$FULL_REFRESH_EVERY" ] || [ "$FORCE_DRAW" = "1" ]; then
        full=yes
        count=0
        eips -f -g "$IMAGE_FILE" 2>>"$LOG_FILE"
        status=$?
    else
        full=no
        eips -g "$IMAGE_FILE" 2>>"$LOG_FILE"
        status=$?
    fi
    echo "$count" > "$COUNTER_FILE" 2>/dev/null

    if [ "$status" -ne 0 ]; then
        log "ERROR: eips exited $status drawing $IMAGE_FILE"
        return 1
    fi
    log "draw ok (full refresh: $full)"
    return 0
}

stop_reader_ui() {
    # The commands that actually work on Kindle firmware, in the order the
    # established dashboards use them. `initctl stop framework` — what this
    # script used before — is not one of them, and its failure was being sent
    # to /dev/null, so the reader carried on repainting over the board while
    # the log said nothing.
    log "stopping the reader UI"
    if [ -x /etc/init.d/framework ]; then
        /etc/init.d/framework stop >>"$LOG_FILE" 2>&1
        log "  /etc/init.d/framework stop -> $?"
    else
        log "  /etc/init.d/framework not present"
    fi
    initctl stop webreader >>"$LOG_FILE" 2>&1
    log "  initctl stop webreader -> $?"

    waited=0
    while [ "$waited" -lt "$UI_STOP_TIMEOUT" ]; do
        ps 2>/dev/null | grep -v grep | grep -q "cvm" || break
        sleep 1
        waited=$((waited + 1))
    done
    if ps 2>/dev/null | grep -v grep | grep -q "cvm"; then
        log "WARN: the reader UI is still running after ${waited}s"
    else
        log "reader UI gone after ${waited}s"
    fi
    sleep "$UI_SETTLE"
    return 0
}

# ─── Sleep ───────────────────────────────────────────────────────

arm_wake_alarm() {
    # Returns 0 only when an alarm is genuinely set. Nothing suspends this
    # device unless that is true: a suspend without a wake alarm is indefinite,
    # and on a frame hanging on a wall it looks exactly like a crash.
    seconds="$1"
    for rtc in $RTC_PATHS; do
        [ -w "$rtc" ] || continue
        case "$rtc" in
            *wakeup_enable)
                # i.MX: seconds from now, and only when nothing else has armed it.
                current=$(cat "$rtc" 2>/dev/null)
                case "$current" in
                    ''|*[!0-9]*) current=0 ;;
                esac
                [ "$current" -ne 0 ] && log "wake alarm already armed at $rtc ($current)" && return 0
                printf '%s' "$seconds" > "$rtc" 2>>"$LOG_FILE" || continue
                ;;
            *wakealarm)
                # Generic: clear, then an absolute-or-relative +seconds.
                echo 0 > "$rtc" 2>/dev/null
                printf '+%s' "$seconds" > "$rtc" 2>>"$LOG_FILE" || continue
                ;;
        esac
        armed=$(cat "$rtc" 2>/dev/null)
        if [ -n "$armed" ] && [ "$armed" != "0" ]; then
            log "wake alarm armed via $rtc (${seconds}s)"
            return 0
        fi
        log "WARN: writing to $rtc did not take"
    done
    return 1
}

suspend_for() {
    seconds="$1"
    [ "$seconds" -lt "$MIN_SLEEP" ] && seconds="$MIN_SLEEP"
    [ "$seconds" -gt "$MAX_SLEEP" ] && seconds="$MAX_SLEEP"

    # Draw immediately before sleeping. Whatever paints a sleep screen, the
    # board is the most recent thing on the panel when the device goes down.
    if [ -f "$IMAGE_FILE" ]; then
        eips -g "$IMAGE_FILE" 2>/dev/null
    fi

    # A moment to breathe, so the loop can be stopped by hand before it goes
    # under.
    sleep "$SUSPEND_GRACE"

    if arm_wake_alarm "$seconds"; then
        log "suspending for ${seconds}s"
        echo mem > "$SYS_POWER_STATE" 2>>"$LOG_FILE" && return 0
        log "WARN: $SYS_POWER_STATE refused the write; staying awake"
    else
        log "WARN: no writable wake alarm found; staying awake instead of suspending"
    fi

    # Staying awake costs battery. Suspending with no alarm costs the whole
    # dashboard, until someone picks the device up and holds the power button.
    sleep "$seconds"
    return 0
}

# ─── One cycle ───────────────────────────────────────────────────

cycle() {
    wifi_on

    check=$(http_get "/display/check" "-")
    if [ -z "$check" ]; then
        # With the reader stopped there is nothing left to reconnect the radio,
        # and lipc talks to a framework that is no longer there. ifconfig is the
        # one lever that does not need it. Harmless when the interface is
        # already up, and worth one retry before writing the cycle off.
        log "WARN: no answer from /display/check; bringing wlan0 up and retrying"
        ifconfig wlan0 up 2>>"$LOG_FILE"
        sleep "$RADIO_RETRY_SLEEP"
        check=$(http_get "/display/check" "-")
    fi
    if [ -z "$check" ]; then
        log "ERROR: /display/check returned nothing"
        wifi_off
        return 1
    fi

    remote_hash=$(json_field "$check" "hash")
    now_epoch=$(json_field "$check" "now_epoch")
    next_epoch=$(json_field "$check" "next_refresh_epoch")
    has_image=$(json_field "$check" "has_image")

    if [ "$has_image" != "true" ]; then
        log "server has no board yet"
        wifi_off
        return 1
    fi

    local_hash=""
    [ -f "$HASH_FILE" ] && local_hash=$(cat "$HASH_FILE" 2>/dev/null)

    if [ "$remote_hash" = "$local_hash" ] && [ -f "$IMAGE_FILE" ] && [ "$FORCE_DRAW" = "0" ]; then
        log "unchanged ($remote_hash); not redrawing"
    elif [ "$remote_hash" = "$local_hash" ] && [ -f "$IMAGE_FILE" ]; then
        # The content has not changed, but what is on the panel is unknown —
        # KUAL, the screensaver or a previous run may have painted over it.
        # The hash tracks the board, not the screen.
        log "unchanged ($remote_hash), but redrawing: panel state unknown"
        if draw; then
            FORCE_DRAW=0
            enter_dedicated_mode
        else
            wifi_off
            return 1
        fi
    else
        tmp="$IMAGE_FILE.part"
        if ! http_get "/display" "$tmp"; then
            log "ERROR: download failed"
            rm -f "$tmp"
            wifi_off
            return 1
        fi
        if ! is_png "$tmp"; then
            log "ERROR: downloaded file is not a PNG"
            rm -f "$tmp"
            wifi_off
            return 1
        fi
        mv "$tmp" "$IMAGE_FILE"
        if draw; then
            printf '%s' "$remote_hash" > "$HASH_FILE"
            FORCE_DRAW=0
            log "drew board $remote_hash"
            enter_dedicated_mode
        else
            wifi_off
            return 1
        fi
    fi

    wifi_off

    # Report the server's own idea of the interval, plus a grace period so the
    # next board has been rendered by the time the device asks for it. The
    # caller decides whether to act on it: a single run from KUAL must not put
    # the device to sleep.
    if [ -n "$now_epoch" ] && [ -n "$next_epoch" ] && [ "$next_epoch" -gt "$now_epoch" ]; then
        NEXT_SLEEP=$((next_epoch - now_epoch + WAKE_GRACE))
    else
        log "WARN: no usable schedule in the response; falling back to MIN_SLEEP"
        NEXT_SLEEP="$MIN_SLEEP"
    fi
    return 0
}

# ─── Main ────────────────────────────────────────────────────────

ONCE=0
for arg in "$@"; do
    case "$arg" in
        --once) ONCE=1 ;;
        --dedicated) DEDICATED=1 ;;
        *) echo "unknown argument: $arg" >&2; exit 2 ;;
    esac
done

die_if_unconfigured
NEXT_SLEEP="$MIN_SLEEP"

# Draw on the first pass whatever the hash says: at startup nothing is known
# about what is currently on the panel.
FORCE_DRAW=1

if [ "$ONCE" = "1" ]; then
    # One cycle, no suspend: this is what a KUAL menu entry runs, and what you
    # want in front of you the first time, when the answer to "did it work?"
    # has to arrive before the device goes back to sleep.
    log "glanceboard-dash single run against $BASE_URL"
    rotate_log
    if cycle; then
        log "ok — would sleep ${NEXT_SLEEP}s"
        exit 0
    fi
    log "cycle failed"
    exit 1
fi

log "glanceboard-dash starting against $BASE_URL"

FAILURES=0
while true; do
    rotate_log
    if cycle; then
        FAILURES=0
        suspend_for "$NEXT_SLEEP"
        # Whatever happened while suspended, the panel is not ours to assume.
        # Redrawing on every wake costs one full flash a few times a day and
        # buys a screen that always shows the board.
        FORCE_DRAW=1
    else
        wifi_off
        FAILURES=$((FAILURES + 1))
        log "cycle failed ($FAILURES consecutive); retrying in ${RETRY_SLEEP}s"
        if [ "$FAILURES" -eq "$FAILS_BEFORE_NOTICE" ]; then
            show_failure_notice
        fi
        suspend_for "$RETRY_SLEEP"
    fi
done
