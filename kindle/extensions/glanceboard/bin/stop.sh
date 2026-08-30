#!/bin/sh
# Stop the loop and let the device behave normally again.
PIDFILE=/mnt/us/glanceboard/state/dash.pid

if [ -f "$PIDFILE" ]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null
    rm -f "$PIDFILE"
fi

lipc-set-prop com.lab126.powerd preventScreenSaver 0 2>/dev/null
initctl start framework 2>/dev/null
initctl start powerd 2>/dev/null
