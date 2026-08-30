#!/bin/sh
# Dedicated mode: stop the reader UI so nothing can repaint over the board.
#
# One way in: stopping the framework stops KUAL too, so afterwards this device
# is a picture frame until you restart it. Hold the power button for about
# twenty seconds to get the reader back.
#
# Use this once the loop has proven itself from "Avvia ciclo". It is the better
# end state — nothing repaints the panel, and the battery lasts longer — but it
# is not where to start.
LOG=/mnt/us/glanceboard/glanceboard.log
PIDFILE=/mnt/us/glanceboard/state/dash.pid

mkdir -p /mnt/us/glanceboard/state 2>/dev/null

if [ -f "$PIDFILE" ]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null
    rm -f "$PIDFILE"
fi

eips -c
eips 0 2 "Glanceboard: modalita' dedicata."
eips 0 4 "Il lettore e KUAL vengono fermati."
eips 0 6 "Per tornare al lettore: tieni premuto"
eips 0 7 "il tasto di accensione ~20 secondi."
sleep 5

initctl stop framework 2>/dev/null
initctl stop powerd 2>/dev/null

nohup sh /mnt/us/glanceboard/glanceboard-dash.sh >> "$LOG" 2>&1 &
echo $! > "$PIDFILE"
