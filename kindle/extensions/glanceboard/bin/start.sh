#!/bin/sh
# Run the refresh loop with the reader left running.
#
# This does NOT stop the framework. An earlier version did, which also stopped
# KUAL — the only way into this device, since it has no SSH — and left a screen
# that looked frozen with no way back except a hard restart. A menu entry must
# not be able to take away the menu.
#
# Nothing is cleared here either: an earlier version wiped the panel and wrote a
# confirmation on it, and the loop then declined to redraw because the board's
# content had not changed. The loop draws on its first pass; leave the screen
# alone until it does.
LOG=/mnt/us/glanceboard/glanceboard.log
PIDFILE=/mnt/us/glanceboard/state/dash.pid

mkdir -p /mnt/us/glanceboard/state 2>/dev/null

if [ -f "$PIDFILE" ]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null
    rm -f "$PIDFILE"
fi

# The screensaver is what would otherwise paint over the board.
lipc-set-prop com.lab126.powerd preventScreenSaver 1 2>/dev/null

nohup sh /mnt/us/glanceboard/glanceboard-dash.sh >> "$LOG" 2>&1 &
echo $! > "$PIDFILE"
