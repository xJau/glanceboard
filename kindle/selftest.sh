#!/usr/bin/env bash
# Exercise the device script against a real server, with fake Kindle binaries.
#
# Every bug that reached the panel lived in glanceboard-dash.sh, and none of
# them could have been caught by reading it: a blank screen because the hash
# said "unchanged" while the panel had been wiped, a menu entry that removed
# the menu, a log with every line in it twice. This runs the script for real —
# same code path the Kindle takes — with eips and lipc-* replaced by recorders.
#
# Usage:  kindle/selftest.sh [python]
set -uo pipefail

PYTHON="${1:-.venv/bin/python}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
PORT=8137
STUB_PORT=8138
TOKEN="selftest-token-long-enough-for-the-check"
PASS=0
FAIL=0

cleanup() {
    [ -n "${SERVER_PID:-}" ] && kill "$SERVER_PID" 2>/dev/null
    [ -n "${STUB_PID:-}" ] && kill "$STUB_PID" 2>/dev/null
    wait "${SERVER_PID:-}" "${STUB_PID:-}" 2>/dev/null
    rm -rf "$WORK"
}
trap cleanup EXIT

ok()   { PASS=$((PASS + 1)); printf '  ok    %s\n' "$1"; }
bad()  { FAIL=$((FAIL + 1)); printf '  FAIL  %s\n' "$1"; }
check() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (atteso: $3, ottenuto: $2)"; fi; }

# ─── Fake device binaries ────────────────────────────────────────
mkdir -p "$WORK/bin" "$WORK/state" "$WORK/server"
cat > "$WORK/bin/eips" <<'EOF'
#!/bin/sh
echo "eips $*" >> "$KT/eips.log"
[ -f "$KT/eips_should_fail" ] && exit 1
exit 0
EOF
cat > "$WORK/bin/lipc-set-prop" <<'EOF'
#!/bin/sh
echo "lipc-set-prop $*" >> "$KT/lipc.log"
EOF
cat > "$WORK/bin/lipc-get-prop" <<'EOF'
#!/bin/sh
echo CONNECTED
EOF
chmod +x "$WORK/bin/"*
export KT="$WORK"

conf() {
    # conf <file> <base-url> <token>
    cat > "$1" <<EOF
BASE_URL="$2"
DISPLAY_TOKEN="$3"
STATE_DIR="$WORK/state"
LOG_FILE="$WORK/glanceboard.log"
WIFI_TIMEOUT=3
MIN_SLEEP=5
EOF
}

run() {
    # run <conf> [args...] — the device script, with the fakes on PATH
    GLANCEBOARD_CONF="$1" PATH="$WORK/bin:$PATH" KT="$WORK" \
        sh "$REPO/kindle/glanceboard-dash.sh" "${@:2}" >/dev/null 2>&1
}

# ─── A real server, and a stub that answers like Cloudflare Access ──
export GB_OUTPUT_DIR="$WORK/server" GB_DISPLAY_TOKEN="$TOKEN" GB_PORT="$PORT" \
       GB_TIMEZONE="Europe/Rome" GB_ICAL_URL="" GB_LAT="" GB_LON=""
# exec, so $! is uvicorn itself: killing the subshell would leave the
# server holding the port and the next run would talk to a stale one.
(cd "$REPO" && exec "$PYTHON" -m glanceboard serve >"$WORK/server.log" 2>&1) &
SERVER_PID=$!
disown "$SERVER_PID" 2>/dev/null || true

cat > "$WORK/stub.py" <<'EOF'
import http.server, json, time
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/display/check"):
            body = json.dumps({"hash": "stub1", "has_image": True,
                               "now_epoch": int(time.time()),
                               "next_refresh_epoch": int(time.time()) + 3600}).encode()
            ctype = "application/json"
        else:
            body = b"<!doctype html><title>Sign in</title>" * 40
            ctype = "text/html"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a): pass
http.server.HTTPServer(("127.0.0.1", STUB_PORT_PLACEHOLDER), H).serve_forever()
EOF
sed -i '' "s/STUB_PORT_PLACEHOLDER/$STUB_PORT/" "$WORK/stub.py" 2>/dev/null \
    || sed -i "s/STUB_PORT_PLACEHOLDER/$STUB_PORT/" "$WORK/stub.py"
"$PYTHON" "$WORK/stub.py" >/dev/null 2>&1 &
STUB_PID=$!
disown "$STUB_PID" 2>/dev/null || true

for _ in $(seq 1 30); do
    curl -s -m 2 -o /dev/null "http://127.0.0.1:$PORT/healthz" 2>/dev/null && break
    sleep 1
done

conf "$WORK/conf"      "http://127.0.0.1:$PORT"      "$TOKEN"
conf "$WORK/conf-bad"  "http://127.0.0.1:$PORT"      "wrong-token-but-long-enough-xxxxxxxxx"
conf "$WORK/conf-html" "http://127.0.0.1:$STUB_PORT" "$TOKEN"
conf "$WORK/conf-down" "http://127.0.0.1:8199"       "$TOKEN"

echo "Device script self-test"

# 1 — a device with nothing on it downloads and draws
rm -f "$WORK/eips.log"; rm -rf "$WORK/state"; mkdir -p "$WORK/state"
run "$WORK/conf" --once
check "primo giro: esce con successo" "$?" "0"
check "primo giro: disegna" "$(grep -c 'eips -g' "$WORK/eips.log" 2>/dev/null || echo 0)" "1"
check "primo giro: salva l'hash" "$([ -s "$WORK/state/last_hash" ] && echo si || echo no)" "si"
check "primo giro: scarica un PNG" \
    "$(head -c 4 "$WORK/state/board.png" 2>/dev/null | grep -c PNG || echo 0)" "1"

# 2 — an unchanged board is still drawn: the hash tracks content, not the panel
rm -f "$WORK/eips.log"
run "$WORK/conf" --once
check "hash invariato: ridisegna comunque" \
    "$(grep -c 'eips -g' "$WORK/eips.log" 2>/dev/null || echo 0)" "1"

# 3 — a wrong token fails cleanly and keeps the board that is already there
rm -f "$WORK/eips.log"
run "$WORK/conf-bad" --once
check "token sbagliato: esce con errore" "$?" "1"
check "token sbagliato: non disegna" \
    "$([ -f "$WORK/eips.log" ] && echo si || echo no)" "no"
check "token sbagliato: conserva la board" \
    "$(head -c 4 "$WORK/state/board.png" | grep -c PNG)" "1"

# 4 — an Access login page must never reach the panel
rm -f "$WORK/eips.log"
run "$WORK/conf-html" --once
check "risposta HTML: esce con errore" "$?" "1"
check "risposta HTML: non disegna" "$([ -f "$WORK/eips.log" ] && echo si || echo no)" "no"
check "risposta HTML: nessun file temporaneo" \
    "$(ls "$WORK/state/"*.part 2>/dev/null | wc -l | tr -d ' ')" "0"

# 5 — an unreachable server
run "$WORK/conf-down" --once
check "server irraggiungibile: esce con errore" "$?" "1"

# 6 — a panel that refuses to draw is a failed cycle, not a successful one
touch "$WORK/eips_should_fail"
run "$WORK/conf" --once
check "eips fallisce: il ciclo fallisce" "$?" "1"
rm -f "$WORK/eips_should_fail"

# 7 — the log is what you read on the device; it must not double every line
rm -f "$WORK/glanceboard.log"
GLANCEBOARD_CONF="$WORK/conf" PATH="$WORK/bin:$PATH" KT="$WORK" \
    sh "$REPO/kindle/glanceboard-dash.sh" --once >> "$WORK/glanceboard.log" 2>&1
check "log: nessuna riga duplicata" \
    "$(grep -c 'single run against' "$WORK/glanceboard.log")" "1"

# 8 — a corrupt refresh counter must not break the arithmetic
echo "spazzatura" > "$WORK/state/refresh_count"
run "$WORK/conf" --once
check "contatore corrotto: il ciclo regge" "$?" "0"

echo
echo "passati: $PASS   falliti: $FAIL"
[ "$FAIL" -eq 0 ]
