# Kindle side

A jailbroken Paperwhite wakes, asks the server whether the board changed,
downloads it only if it did, draws it with `eips`, and suspends to RAM until
the next slot.

The board is landscape, so the device is meant to stand on its side. The server
rotates the PNG before serving it, which is what `GB_ROTATE` is for: if the
board comes out upside down for the way you have propped the Kindle, set it to
`270` instead of `90` and nothing on the device has to change.

Nothing here reformats the device or touches the jailbreak. Everything lives in
`/mnt/us/glanceboard/`, and uninstalling means deleting that folder.

## What you need on the device

- A jailbroken Kindle (this is what gives you a shell and `eips`).
- SSH access over USB (USBNetwork) or Wi-Fi, or a KUAL shell extension. The
  files can be copied over USB mass storage, but starting the loop and setting
  it to run at boot both need a shell.

## Install

With the Kindle plugged in and mounted:

```bash
kindle/install-to-kindle.sh
```

On macOS this needs the terminal to have access to removable volumes:
**System Settings → Privacy & Security → Files and Folders → your terminal →
Removable Volumes** (or add it under Full Disk Access and restart it).
Without that, macOS answers `Operation not permitted` for every file on the
device and the script will tell you so.

That copies:

```
/mnt/us/glanceboard/glanceboard-dash.sh
/mnt/us/glanceboard/glanceboard.conf     (from the example, if not already there)
/mnt/us/glanceboard/state/
```

Then eject the Kindle, connect to it over SSH, and fill in the config:

```sh
vi /mnt/us/glanceboard/glanceboard.conf     # BASE_URL and DISPLAY_TOKEN
```

## First run

Stop the reader UI first, or it will redraw over the board:

```sh
initctl stop framework
initctl stop powerd          # optional: stops the device dimming the panel
sh /mnt/us/glanceboard/glanceboard-dash.sh
```

The first cycle logs to `/mnt/us/glanceboard/glanceboard.log`. Read it if the
screen stays blank — `is not a PNG` usually means the token or the Access
service token is wrong and the server returned an error page instead.

To get the reader back:

```sh
initctl start framework
```

## Run it at boot

Create `/etc/upstart/glanceboard.conf` on the device:

```
start on started framework
stop on stopping framework

respawn
respawn limit 10 300

script
    initctl stop framework || true
    exec sh /mnt/us/glanceboard/glanceboard-dash.sh
end script
```

Then `initctl start glanceboard`. On firmware where `/etc` is read-only,
remount it first with `mntroot rw` and put it back with `mntroot ro`
afterwards.

## Battery

The loop suspends to RAM between refreshes (`/sys/class/rtc/rtc1/wakealarm`
plus `/sys/power/state`), and turns the radio off while suspended. With three
slots a day, that is a handful of wake-ups. If the RTC write fails on your
firmware the script falls back to a plain `sleep`, which works but drains the
battery in days rather than weeks — the log says which one is happening.

## TLS

The certificate bundle on Kindle firmware is old, and this is the most likely
thing to break against Cloudflare. If the log shows TLS failures, copy a
current `cacert.pem` onto the device and point `CA_BUNDLE` at it.
`ALLOW_INSECURE_TLS=1` exists for narrowing down a problem and should not be
left on: it disables certificate checking, which throws away the guarantee that
you are talking to your own tunnel.
