#!/bin/sh
# Run the refresh loop with the reader left running.
#
# This does NOT stop the framework. An earlier version did, which also stopped
# KUAL — the only way to reach this device, since it has no SSH — and left the
# user with a screen that looked frozen and no way back except a hard restart.
# A menu entry must not be able to remove access to the menu.
#
# The screensaver is suppressed instead, which is what would otherwise paint
# over the board. The device still suspends between refreshes; a short press of
# the power button wakes it, and the reader is there as usual.
LOG=/mnt/us/glanceboard/glanceboard.log
PIDFILE=/mnt/us/glanceboard/state/dash.pid

mkdir -p /mnt/us/glanceboard/state 2>/dev/null

if [ -f "$PIDFILE" ]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null
    rm -f "$PIDFILE"
fi

lipc-set-prop com.lab126.powerd preventScreenSaver 1 2>/dev/null

nohup sh /mnt/us/glanceboard/glanceboard-dash.sh >> "$LOG" 2>&1 &
echo $! > "$PIDFILE"

eips -c
eips 0 2 "Glanceboard: ciclo avviato."
eips 0 4 "Il lettore resta acceso: puoi sempre"
eips 0 5 "tornare in KUAL e premere Ferma."
