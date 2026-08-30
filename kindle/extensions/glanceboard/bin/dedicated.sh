#!/bin/sh
# Dedicated mode: the board and nothing else.
#
# This script does NOT stop the reader UI. It starts the loop and gets out of
# the way; the loop stops the framework itself, once it has a board on the
# panel.
#
# Doing it here was wrong twice over. Stopping the framework kills KUAL, and
# with it this very script — so the loop was never started and the device was
# left blank, with nothing running and no way back in. And it happened before
# the first fetch, so a failure at that moment took away the reader and gave
# nothing in return.
#
# To get the reader back afterwards, hold the power button for about twenty
# seconds. Nothing here starts at boot, so a restart always lands in the reader.
LOG=/mnt/us/glanceboard/glanceboard.log
PIDFILE=/mnt/us/glanceboard/state/dash.pid

mkdir -p /mnt/us/glanceboard/state 2>/dev/null

if [ -f "$PIDFILE" ]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null
    rm -f "$PIDFILE"
fi

eips 0 2 "Glanceboard: modalita' dedicata" 2>/dev/null
eips 0 3 "Attendo la board, poi fermo il lettore." 2>/dev/null

# setsid detaches from KUAL's session, so stopping the framework later cannot
# take the loop down with it. nohup alone does not survive that.
if command -v setsid >/dev/null 2>&1; then
    setsid sh /mnt/us/glanceboard/glanceboard-dash.sh --dedicated >> "$LOG" 2>&1 &
else
    nohup sh /mnt/us/glanceboard/glanceboard-dash.sh --dedicated >> "$LOG" 2>&1 &
fi
echo $! > "$PIDFILE"
