#!/bin/sh
# Turn the Kindle into the dashboard: stop the reader UI and run the loop.
#
# Stopping the framework also stops KUAL, so "Ferma dashboard" is no longer
# reachable from the menu afterwards. To get the reader back, hold the power
# button for about twenty seconds and let the device restart.
LOG=/mnt/us/glanceboard/glanceboard.log
PIDFILE=/mnt/us/glanceboard/state/dash.pid

mkdir -p /mnt/us/glanceboard/state 2>/dev/null

if [ -f "$PIDFILE" ]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null
    rm -f "$PIDFILE"
fi

eips -c
eips 0 2 "Glanceboard: avvio dashboard..."
eips 0 4 "Per tornare al lettore: tieni premuto"
eips 0 5 "il tasto di accensione ~20 secondi."

initctl stop framework 2>/dev/null
initctl stop powerd 2>/dev/null

nohup sh /mnt/us/glanceboard/glanceboard-dash.sh >> "$LOG" 2>&1 &
echo $! > "$PIDFILE"
