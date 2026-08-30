#!/bin/sh
# Stop the loop and bring the reader back.
#
# Only reachable while the framework is still running — that is, after "Un giro
# adesso", not after "Avvia dashboard". In that case, restart the device.
PIDFILE=/mnt/us/glanceboard/state/dash.pid

if [ -f "$PIDFILE" ]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null
    rm -f "$PIDFILE"
fi

initctl start framework 2>/dev/null
initctl start powerd 2>/dev/null
