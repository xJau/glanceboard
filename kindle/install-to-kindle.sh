#!/usr/bin/env bash
# Copy the dash script and a config template onto a Kindle mounted over USB.
#
# This only ever writes into one new directory on the device's user storage. It
# does not delete anything, does not touch the jailbreak, and does not format.
# Everything it writes can be removed by deleting that one folder.
#
# Usage:
#   kindle/install-to-kindle.sh [/Volumes/Kindle]
set -euo pipefail

VOLUME="${1:-/Volumes/Kindle}"
TARGET="$VOLUME/glanceboard"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -d "$VOLUME" ]; then
    echo "No volume at $VOLUME — is the Kindle plugged in and mounted?" >&2
    exit 1
fi

if ! ls "$VOLUME" >/dev/null 2>&1; then
    cat >&2 <<'MSG'
The volume is mounted but macOS is refusing access to it.

Grant your terminal access to removable volumes:
  System Settings → Privacy & Security → Files and Folders
    → your terminal app → enable "Removable Volumes"
  (or add the terminal under Full Disk Access, then restart it)

Then run this script again.
MSG
    exit 1
fi

mkdir -p "$TARGET/state"
cp "$HERE/glanceboard-dash.sh" "$TARGET/glanceboard-dash.sh"
chmod +x "$TARGET/glanceboard-dash.sh" 2>/dev/null || true

if [ -f "$TARGET/glanceboard.conf" ]; then
    echo "Keeping the existing $TARGET/glanceboard.conf"
else
    cp "$HERE/glanceboard.conf.example" "$TARGET/glanceboard.conf"
    echo "Wrote a config template to $TARGET/glanceboard.conf"
fi

echo
echo "Installed into $TARGET"
echo "On the device this path is /mnt/us/glanceboard"
echo
echo "Next, on the Kindle itself (over SSH or a KUAL shell):"
echo "  1. edit /mnt/us/glanceboard/glanceboard.conf — BASE_URL and DISPLAY_TOKEN"
echo "  2. sh /mnt/us/glanceboard/glanceboard-dash.sh   # watch one cycle"
echo "  3. see kindle/README.md for starting it at boot"
