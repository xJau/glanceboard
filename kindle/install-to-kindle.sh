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

# KUAL extension, so the device can be driven from its own menu without SSH.
EXT="$VOLUME/extensions/glanceboard"
mkdir -p "$EXT/bin"
cp "$HERE/extensions/glanceboard/menu.json" "$EXT/menu.json"
# KUAL builds that predate menu-only extensions need this descriptor,
# and silently ignore the whole directory without it.
cp "$HERE/extensions/glanceboard/config.xml" "$EXT/config.xml"
cp "$HERE/extensions/glanceboard/bin/"*.sh "$EXT/bin/"
chmod +x "$EXT/bin/"*.sh 2>/dev/null || true
echo "KUAL extension installed into $EXT"

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
echo "Next, on the Kindle itself — no SSH needed:"
echo "  1. make sure glanceboard.conf has BASE_URL, DISPLAY_TOKEN and the CF_ACCESS_* pair"
echo "  2. eject the Kindle, open KUAL, and pick Glanceboard > Un giro adesso"
echo "  3. if nothing appears, Glanceboard > Mostra log"
