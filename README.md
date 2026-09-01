<!--
Copyright 2026 Google LLC
Copyright 2026 Glanceboard Kindle contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
-->

# Glanceboard for Kindle

A daily board — date, temperatures, appointments — rendered as a grayscale PNG
and drawn on a jailbroken Kindle Paperwhite.

A fork of [google-gemini/glanceboard](https://github.com/google-gemini/glanceboard),
which targets a 6-colour Waveshare e-ink frame and generates the whole picture
with an image model. This fork keeps the calendar and weather sources and
replaces everything else.

## What is different from upstream

| | Upstream | Here |
|---|---|---|
| Display | Waveshare 7.3", 800×480, 6 colours | Kindle Paperwhite, 16 grays, landscape board on a portrait panel |
| Layout | Drawn by an image model from a prompt | Drawn by PIL, deterministically |
| Config | `data/config.json`, editable over HTTP | Environment variables only |
| `/api/config` | Served the API key unauthenticated | Does not exist |
| Bind address | `0.0.0.0` | `127.0.0.1` by default |
| Display endpoint | Unauthenticated | Token required, checked by the server itself |
| Removed | dashboard, Firebase functions, Gmail, widgets, characters | |

Running on a Paperwhite 4. Phase 1 — calendar, weather, the deterministic board
— shipped as `v0.1.0`; phase 2 adds the illustration described below.

## The layout

The picture is the page. Everything else sits on top of it: a small ribbon with
the date, the day as a timetable down the left, the weather floating in the
corner, and a caption in the margin. Only the outer frame is drawn as a line —
there are no cards.

```
┌──────────────────────────────────────────────────────────┐
│  IN PROGRAMMA OGGI · · · · · · · · · · · · · ·  ☁ 30°    │
│        —  │ Studio chiuso il pomeriggio · · ·   Coperto  │
│     09:00 │ Consulenza Rossi · · · the illustration, · · │
│     11:30 │ Call Bianchi SRL · · · washed pale, filling  │
│     14:00 │ Sopralluogo cantiere · the whole page · · ·  │
│     18:30 │ Palestra · · · · · · · · · · · · · · · · · · │
│  · · · · · · · ╲___ Martedì 1 settembre ___╱ · · · · · · │
│  aggiornato alle 05:00 · · · · · · · · · · · · · · · · · │
└──────────────────────────────────────────────────────────┘
```

The ribbon hangs along the bottom, bowed downwards the way a banner hangs from
its two ends. The band curves and the type stays level: setting the letters
along the arc would mean rotating each one, and rotated glyphs on a sixteen-grey
panel come out ragged.

The board is composed at 1448×1072 and rotated a quarter turn on the way out,
because the Paperwhite panel is physically portrait. `GB_ROTATE` decides which
way; `--upright` skips it while you are looking at the PNG on a desk.

Legibility over a photograph is the whole problem. Two things solve it, and
both are adjustable. The picture is washed towards the paper — `GB_ART_WASH`,
at `0.62` by default — and the two regions that carry type are lifted a little
further under a blurred veil, so the edge reads as light falling off rather
than as a box. No wash strong enough to guarantee contrast over *any*
photograph would leave a picture worth having, which is why there is a veil at
all.

The day is set as a timetable: hours right-aligned in their own column, a rule,
then the entries. The eye finds *what time* and *what* in two fixed places
instead of reading along a sentence. All-day entries get a dash, the way a
timetable says "no fixed hour".

Rows compact before anything is dropped: first the spacing, then the type size,
and only then does a day too full to fit end with *e altri 2 appuntamenti*.

## The illustration

The panel on the right holds a photograph of your own, restyled by an image
model into a storybook illustration. One photo a day, taken from a local
directory and rotated through it without repeats, chosen once and remembered —
the board regenerates three times a day, and neither paying three times nor
watching the picture change at lunch is what anyone wants. The result is cached
on disk, so a day costs a single call.

Two properties matter more than the picture:

**The model never sees the calendar.** The request carries a style instruction
and a photograph. There is no path by which an appointment reaches it, and a
test asserts as much — which is stricter than filtering a payload, because
there is no payload to filter.

**The library is separate from where the photos came from.** A public Google
Photos album can top it up before each render, but reading a share page is not
a documented interface — Google removed the read-only Library API scopes in
March 2025, shared-album endpoints answer `403`, and the Picker API that
replaced them needs a person to choose photos every time. So the sync only ever
*adds files to a directory*, and everything downstream reads that directory. The
day Google changes the page, the sync says so in the log and the board carries
on with the photographs already on disk.

**A failure costs the picture and nothing else.** No key, no photos, a model
that will not answer: the panel stays empty and the board ships with its
appointments and its weather. The deterministic renderer is not a fallback path
that rots between failures — it is the path that runs every day, with one region
filled in when the picture arrives.

Set `GB_ILLUSTRATION=0` to switch it off, or `GB_ART_FRACTION=0` to give the
whole board to the agenda.

To work on the layout without spending anything:

```bash
.venv/bin/python -m glanceboard render --sample --illustration any.png --upright --out out/board.png
```

Rows compact before anything is dropped: first the spacing, then the type size,
and only then does a day too full to fit end with *e altri 2 appuntamenti*.

Set `GB_ART_FRACTION=0` to give the whole board to the agenda until phase 2
arrives.

## Local development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

Render the bundled sample without any configuration, network or server:

```bash
.venv/bin/python -m glanceboard render --sample --out out/board.png --open
```

That is the loop for iterating on the layout. Useful flags:

```bash
--size 1648x1236     # a Paperwhite 5/6 panel
--upright            # skip GB_ROTATE, easier to look at on screen
--debug-regions      # outline the ribbon, agenda, illustration panel and weather card
--date 2026-09-01    # a specific day
--ics path.ics       # a real feed saved to a file
```

Render today from the live sources instead:

```bash
cp .env.example .env    # fill in GB_ICAL_URL, GB_LAT, GB_LON
set -a; source .env; set +a
.venv/bin/python -m glanceboard render --out out/board.png
```

Run the tests:

```bash
.venv/bin/python -m pytest tests -q
```

## Running the server

```bash
python3 -m glanceboard token      # generate GB_DISPLAY_TOKEN
python3 -m glanceboard serve
```

Three endpoints, all read-only:

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /display` | token | The PNG. Sends an `ETag`; answers `304` if unchanged. |
| `GET /display/check` | token | Current hash, plus `now_epoch` and `next_refresh_epoch`. |
| `GET /healthz` | none | Liveness for the container healthcheck. |

There is no way to write configuration over HTTP, and no endpoint that can read
a secret out to a client. The token may travel in the query string, because
BusyBox wget on an old Kindle cannot always set a header, so an access-log
filter redacts it — otherwise every request the device made would write the
credential into the container log in clear text.

The board is regenerated at each hour in `GB_SLOTS`, and once on every startup —
a restart usually means something changed. An unchanged day keeps its existing
PNG, so the hash, and therefore the device's decision not to redraw, stays
stable.

The hash includes `glanceboard.__version__`. **Bump it whenever you change how
the board looks**, or the redesign will reach the Kindle only when the calendar
or the weather happens to move.

## Deploying on the Pi

```bash
cp .env.example .env     # fill it in, including GB_DISPLAY_TOKEN
docker compose up -d --build
```

The compose file deliberately publishes no ports. The container is reachable
only from Caddy on the shared network:

```
glanceboard.example.com {
    reverse_proxy glanceboard:8000
}
```

Then put the hostname behind the Cloudflare Tunnel, and add a Cloudflare Access
policy with a **service token** so the Kindle can authenticate without a
browser. The device sends `CF-Access-Client-Id` and `CF-Access-Client-Secret`
alongside its own bearer token.

Those are two independent checks on purpose. Access is the outer door; the
bearer token is checked by this server whatever route the request arrived by, so
a misconfigured Access policy, or someone on the LAN reaching the container
directly, still gets a `401`.

Step by step, including the Access policy that has to use the **Service Auth**
action rather than `Allow`: [docs/deploy.md](docs/deploy.md).

## Configuration

Everything comes from the environment. Any variable `GB_X` can instead be given
as `GB_X_FILE` pointing at a file, for Docker secrets.

| Variable | Default | Meaning |
|---|---|---|
| `GB_ICAL_URL` | — | Private iCal feed. Secret. |
| `GB_TIMEZONE` | `Europe/Rome` | Used for the day boundary and the slots. |
| `GB_LAT`, `GB_LON` | — | Weather location. Omit to skip weather. |
| `GB_TEMP_UNIT` | `celsius` | `celsius` or `fahrenheit`. |
| `GB_WIDTH`, `GB_HEIGHT` | `1448`, `1072` | Landscape canvas. PW5/PW6: `1648`, `1236`. |
| `GB_ROTATE` | `90` | Quarter turns applied to the PNG. `0`, `90`, `180`, `270`. |
| `GB_ART_WASH` | `0.62` | How far the picture is washed towards the paper. |
| `GB_MAX_EVENTS` | `12` | Upper bound before the `+N altri` note. |
| `GB_SLOTS` | `5,12,18` | Hours at which the board is regenerated. |
| `GB_DISPLAY_TOKEN` | — | Required to serve. At least 24 characters. |
| `GB_ALLOW_NO_TOKEN` | `0` | Local development escape hatch. |
| `GB_BIND_HOST` | `127.0.0.1` | The image sets `0.0.0.0`; the port is not published. |
| `GB_PORT` | `8000` | |
| `GB_OUTPUT_DIR` | `./data` | PNG and state. `/data` in the container. |
| `GB_FONT_DIR` | `./assets/fonts` | |
| `GB_REQUEST_TIMEOUT` | `20` | Seconds, for both sources. |
| `GB_GEMINI_API_KEY` | — | Image model key. Secret. Absent means no illustration. |
| `GB_ILLUSTRATION` | `1` | Switches the picture off without touching anything else. |
| `GB_ILLUSTRATION_MODEL` | `gemini-2.5-flash-image` | |
| `GB_PHOTO_DIR` | `./data/photos` | The photo library. |
| `GB_PHOTO_ALBUM_URL` | — | A public Google Photos album to top it up from. |
| `GB_PHOTO_SYNC` | `1` | Stops the sync without forgetting the album. |
| `GB_PHOTO_LIMIT` | `60` | How many photos to keep from the album. |
| `GB_STYLE_PROMPT` | — | Overrides the built-in style instruction. |

## Client data

The photographs are sent to the image model, which is the one thing here that
leaves the house. Nothing else does: the calendar is read locally, and the
model is given a picture and a style, never a schedule.

The calendar carries client information — addresses, notes, attendee emails.
`parse_ical` keeps four fields per event (title, start, end, all-day) and
discards the rest at the point of parsing, so nothing downstream can leak what
it never received. `Board.to_dict()` is the shape a phase-2 model payload will
take, and `tests/test_privacy.py` asserts that a feed full of client details
produces a payload containing none of them.

If you add a field to `Event`, you are moving that boundary. Do it deliberately.

## Failure behaviour

Neither source can take the board down. Each is tried three times with a short
backoff before it is written off — Open-Meteo answered `503` on an ordinary
afternoon, and without the retry a few seconds of outage cost the board its
weather until the next slot, six hours later. An unreachable calendar then
renders as *Calendario non raggiungibile*, a failed weather call as `—` and a
footer note.
The PNG is written atomically, so a device polling mid-render gets the previous
board rather than half a file, and a render that raises leaves the last good
PNG in place.

## The Kindle

Driven from a KUAL menu, because this Paperwhite has no SSH. `kindle/install-to-kindle.sh`
copies the loop and the menu onto the device over USB; nothing else is needed on
it.

| Entry | |
|---|---|
| **Un giro di prova** | one cycle, no suspend, reader untouched |
| **Avvia cornice** | the frame proper |
| **Mostra log** | the log, drawn on the panel — the only way to read it without a shell |
| **Avvia col lettore acceso** | for debugging; a stray touch brings the home screen back |

The loop asks `/display/check` first and downloads only when the hash has moved,
draws with a single `eips -f -g`, and suspends until the next slot. It sleeps for
the difference between two epoch values the server sends, so a Kindle clock —
which runs in UTC and drifts while suspended — is never trusted for scheduling.

Three rules the device side earned the hard way:

- **The reader is stopped only once a board is on the panel**, and by the loop
  itself rather than by the menu script that KUAL is hosting. Stopping it any
  earlier took the interface away from a device that then had nothing to show.
- **Nothing suspends without a wake alarm that has been read back.** Staying
  awake costs battery; suspending with no alarm costs the whole dashboard until
  someone holds the power button.
- **A failure is reported over the board, never instead of it.** Yesterday's
  appointments plus a line of explanation beat a white page with a log on it.

Full details, including how to get the reader back: [kindle/README.md](kindle/README.md).

## Testing

```bash
.venv/bin/python -m pytest        # 110 tests
kindle/selftest.sh                # 31 checks against the device script
```

Neither touches the network.

The Python tests cover recurrence expansion and timezone conversion, the privacy
assertions, panel fit — at most 16 grays, every one a multiple of 17 — render
determinism, that nothing is drawn into the reserved illustration panel, atomic
writes, and every authentication path including the absence of a config
endpoint.

`kindle/selftest.sh` runs `glanceboard-dash.sh` for real against a server it
starts itself, with `eips` and `lipc-*` replaced by recorders and fake sysfs
files standing in for the wake alarm. It covers a first draw on an empty device,
an unchanged board that must be redrawn anyway because the panel's state is
unknown, a wrong token, an Access login page arriving where a PNG was expected,
a panel that refuses to draw, the handover into the frame, and a device with no
writable alarm.

Every defect that reached the panel lived in that script, and none of them would
have been caught by reading it.

## Licence

Apache 2.0, inherited from the upstream project. The bundled
[Nunito](https://github.com/googlefonts/nunito) typeface is under the SIL Open
Font License; see `assets/fonts/OFL.txt`.
