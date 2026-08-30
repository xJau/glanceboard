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
LOG_MAX_BYTES=131072

# shellcheck source=/dev/null
[ -f "$CONF_FILE" ] && . "$CONF_FILE"

IMAGE_FILE="$STATE_DIR/board.png"
HASH_FILE="$STATE_DIR/last_hash"
COUNTER_FILE="$STATE_DIR/refresh_count"

mkdir -p "$STATE_DIR" 2>/dev/null

log() {
    printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S')" "$*" >> "$LOG_FILE" 2>/dev/null
    printf '%s\n' "$*"
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

is_png() {
    [ -s "$1" ] || return 1
    head -c 4 "$1" 2>/dev/null | grep -q 'PNG'
}

draw() {
    count=0
    [ -f "$COUNTER_FILE" ] && count=$(cat "$COUNTER_FILE" 2>/dev/null || echo 0)
    count=$((count + 1))

    if [ "$count" -ge "$FULL_REFRESH_EVERY" ]; then
        # A full flash every so often; partial updates leave ghosting behind.
        eips -c 2>/dev/null
        eips -c 2>/dev/null
        count=0
    fi
    echo "$count" > "$COUNTER_FILE" 2>/dev/null

    eips -g "$IMAGE_FILE" 2>/dev/null || {
        log "ERROR: eips failed to draw $IMAGE_FILE"
        return 1
    }
    return 0
}

# ─── Sleep ───────────────────────────────────────────────────────

suspend_for() {
    seconds="$1"
    [ "$seconds" -lt "$MIN_SLEEP" ] && seconds="$MIN_SLEEP"
    [ "$seconds" -gt "$MAX_SLEEP" ] && seconds="$MAX_SLEEP"
    log "sleeping ${seconds}s"

    if [ -w /sys/class/rtc/rtc1/wakealarm ]; then
        echo 0 > /sys/class/rtc/rtc1/wakealarm 2>/dev/null
        if echo "+$seconds" > /sys/class/rtc/rtc1/wakealarm 2>/dev/null; then
            # Suspend to RAM. If the write fails the shell simply sleeps, which
            # costs battery but never leaves the device awake with a stale board.
            echo mem > /sys/power/state 2>/dev/null && return 0
        fi
    fi
    sleep "$seconds"
}

# ─── One cycle ───────────────────────────────────────────────────

cycle() {
    wifi_on

    check=$(http_get "/display/check" "-")
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

    if [ "$remote_hash" = "$local_hash" ] && [ -f "$IMAGE_FILE" ]; then
        log "unchanged ($remote_hash); not redrawing"
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
            log "drew board $remote_hash"
        else
            wifi_off
            return 1
        fi
    fi

    wifi_off

    # Sleep for the server's own idea of the interval, plus a grace period so
    # the next board has been rendered by the time the device asks for it.
    if [ -n "$now_epoch" ] && [ -n "$next_epoch" ] && [ "$next_epoch" -gt "$now_epoch" ]; then
        suspend_for $((next_epoch - now_epoch + WAKE_GRACE))
    else
        log "WARN: no usable schedule in the response; falling back to MIN_SLEEP"
        suspend_for "$MIN_SLEEP"
    fi
    return 0
}

# ─── Main ────────────────────────────────────────────────────────

die_if_unconfigured
log "glanceboard-dash starting against $BASE_URL"

while true; do
    rotate_log
    if ! cycle; then
        wifi_off
        log "cycle failed; retrying in ${RETRY_SLEEP}s"
        suspend_for "$RETRY_SLEEP"
    fi
done
