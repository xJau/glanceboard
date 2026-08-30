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
| **Avvia ciclo (lettore acceso)** | Runs the loop with the reader still running. Reversible. |
| **Ferma ciclo** | Stops the loop. |
| **Modalita dedicata (spegne KUAL)** | Stops the reader UI. One way in — see below. |

*Un giro adesso* is the safe one: it draws the board and leaves everything else
alone, so a failed attempt costs nothing. If the screen stays blank, the log is
one entry away — `is not a PNG` usually means the server returned an error page
instead of an image, which points at the token or the Access policy.

*Avvia ciclo* runs the refresh loop with the reader left alone. Use it to prove
the loop works, not as the end state: the reader is alive underneath the board,
and it shows. The airplane icon appears whenever the loop turns the radio off
between refreshes, the power manager still dims the front light, and a stray
touch brings the home screen back over the board. All three are the framework
doing its job. *Ferma ciclo* undoes it.

*Modalita dedicata* is the end state, and it removes all three at once by
removing their cause: the framework stops, so nothing repaints the panel, the
front light goes off — an e-ink board does not need one — and the battery lasts
considerably longer.

The board is drawn again after the framework stops — it clears the panel on its
way out, so drawing only before it goes left a white page until the next slot.

The radio switch belongs to the framework too (`com.lab126.cmd`), so once it is
gone the loop stops trying to turn the radio off between refreshes and leaves it
on. That costs battery. It is the price of not having a framework to ask, and
the log says when it happens.

Both the framework and `powerd` are stopped: `powerd` is what paints the sleep
screen, so leaving it running covered the board with a battery gauge and a clock
the first time the device suspended. Suspending needs nothing from it — the loop
writes to the RTC and `/sys/power/state` itself — and the front light is set
before it goes.

The menu entry does not stop anything itself. It starts the loop, detached, and
the loop stops the framework once it has a board on the panel — so a device that
cannot reach the server keeps its reader instead of being left blank, and the
command that kills KUAL is never issued by a script that KUAL is hosting.

It is still a one-way door on a device without SSH: stopping the framework also
stops KUAL, so the way back to the reader is holding the power button for about
twenty seconds. That exit always works, because nothing here starts at boot: a
restart always lands you back in the reader.

*Avvia ciclo* also disables `pillow`, the service that draws the status bar and
the system dialogs — the battery, the charging bolt, the airplane icon. That
keeps the reader's chrome off the board without stopping the reader. The touch
layer is still live underneath, so a stray tap still brings the home screen
back; only dedicated mode removes that.

The charge LED on the bottom edge is hardware. Nothing on the device can turn
it off.

If a cycle fails three times in a row, the panel says so and shows the tail of
the log. Without that, a loop that has been broken since Tuesday looks exactly
like a board that has nothing new to show.

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

## Testing the device script without a device

```bash
kindle/selftest.sh
```

Runs `glanceboard-dash.sh` for real against a server it starts itself, with
`eips` and `lipc-*` replaced by recorders. It covers the cases that actually
went wrong: a first draw on an empty device, an unchanged board that must be
redrawn anyway because the panel's state is unknown, a wrong token, an Access
login page arriving where a PNG was expected, an unreachable server, a panel
that refuses to draw, and a log that must not contain every line twice.

Every bug that reached the panel lived in this script, and none of them would
have been caught by reading it.

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
