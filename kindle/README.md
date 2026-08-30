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

- A jailbroken Kindle with **KUAL**. That is enough: the installer ships a KUAL
  extension, so nothing here needs a shell on the device.
- SSH (USBNetwork) is optional. It makes debugging easier, but every step below
  can be done from the Kindle's own menu.

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
/mnt/us/extensions/glanceboard/          (the KUAL menu)
```

Fill in `glanceboard.conf` while the device is still mounted — `BASE_URL`,
`DISPLAY_TOKEN`, and the `CF_ACCESS_*` pair if the hostname is behind a
Cloudflare Access policy.

## First run, from KUAL

Eject the Kindle, open KUAL, and you will find a **Glanceboard** menu:

| Entry | What it does |
|---|---|
| **Un giro adesso (prova)** | One cycle, no suspend, reader left running. Start here. |
| **Mostra log** | Draws the tail of the log on the panel. The only way to read it without SSH. |
| **Avvia dashboard** | Stops the reader UI and runs the loop for real. |
| **Ferma dashboard** | Stops the loop and brings the reader back. |

*Un giro adesso* is the safe one: it draws the board and leaves everything else
alone, so a failed attempt costs nothing. If the screen stays blank, the log is
one entry away — `is not a PNG` usually means the server returned an error page
instead of an image, which points at the token or the Access policy.

Once that works, *Avvia dashboard* stops the framework and starts the loop.
**That also stops KUAL**, so *Ferma dashboard* is no longer reachable
afterwards: to get the reader back, hold the power button for about twenty
seconds and let the device restart.

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
