#!/bin/sh
# One cycle, no suspend, framework left running.
#
# This is the entry to use first: the board is drawn and the reader comes back
# on its own, so a failed attempt costs nothing and the log is one menu entry
# away.
LOG=/mnt/us/glanceboard/glanceboard.log

eips -c
eips 0 2 "Glanceboard: scarico la board..."

sh /mnt/us/glanceboard/glanceboard-dash.sh --once >> "$LOG" 2>&1
status=$?

if [ "$status" -ne 0 ]; then
    sleep 1
    sh /mnt/us/extensions/glanceboard/bin/showlog.sh
fi
exit "$status"
