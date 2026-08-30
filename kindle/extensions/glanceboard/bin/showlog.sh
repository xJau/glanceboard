#!/bin/sh
# Draw the tail of the log on the panel.
#
# Without SSH this is the only way to read it, so it is a first-class menu
# entry rather than a debugging afterthought.
LOG=/mnt/us/glanceboard/glanceboard.log

eips -c
eips 0 1 "--- glanceboard.log ---"
if [ ! -f "$LOG" ]; then
    eips 0 3 "nessun log: non ha ancora girato"
    exit 0
fi

# eips prints at character cells; 72 columns is about what fits.
tail -n 22 "$LOG" | cut -c1-72 | (
    row=3
    while read -r line; do
        eips 0 "$row" "$line"
        row=$((row + 1))
    done
)
