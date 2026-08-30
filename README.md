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
| Display | Waveshare 7.3", 800×480, 6 colours, landscape | Kindle Paperwhite, portrait, 16 grays |
| Layout | Drawn by an image model from a prompt | Drawn by PIL, deterministically |
| Config | `data/config.json`, editable over HTTP | Environment variables only |
| `/api/config` | Served the API key unauthenticated | Does not exist |
| Bind address | `0.0.0.0` | `127.0.0.1` by default |
| Display endpoint | Unauthenticated | Token required, checked by the server itself |
| Removed | dashboard, Firebase functions, Gmail, widgets, characters | |

Phase 1 — what is here — generates no images and calls no models.

## The layout

```
┌────────────────────────────────────────┐
│ Martedì                      18° / 28° │  header: day, date, min/max
│ 1 settembre 2026              Coperto  │
├────────────────────────────────────────┤
│ tutto il giorno   Studio chiuso        │  agenda: time on the left,
│ 09:00             Consulenza Rossi     │  title on the right
│ 10:00                                  │
│ 11:30             Call Bianchi SRL     │
│ …                                      │
├────────────────────────────────────────┤
│                                        │
│         (illustration band)            │  reserved, empty in phase 1
│                                        │
├────────────────────────────────────────┤
│ aggiornato 05:00                       │
└────────────────────────────────────────┘
```

The illustration band is reserved now even though nothing draws into it. When
phase 2 adds an image model, it fills that band and nothing else: the text stays
deterministic, so a model can never restate an appointment time incorrectly, and
a failed generation costs the board its picture rather than its content. The
deterministic renderer is not a separate fallback path that rots unused — it is
the same path that runs every day.

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
--size 1072x1448     # a Paperwhite 3/4 panel
--debug-regions      # outline the header, agenda, illustration and footer
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
a secret out to a client.

The board is regenerated at each hour in `GB_SLOTS`, and once at startup if the
stored board is not from today. An unchanged day keeps its existing PNG, so the
hash — and therefore the device's decision not to redraw — stays stable.

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

## Configuration

Everything comes from the environment. Any variable `GB_X` can instead be given
as `GB_X_FILE` pointing at a file, for Docker secrets.

| Variable | Default | Meaning |
|---|---|---|
| `GB_ICAL_URL` | — | Private iCal feed. Secret. |
| `GB_TIMEZONE` | `Europe/Rome` | Used for the day boundary and the slots. |
| `GB_LAT`, `GB_LON` | — | Weather location. Omit to skip weather. |
| `GB_TEMP_UNIT` | `celsius` | `celsius` or `fahrenheit`. |
| `GB_WIDTH`, `GB_HEIGHT` | `1236`, `1648` | Panel size. PW3/PW4: `1072`, `1448`. |
| `GB_ART_FRACTION` | `0.30` | Share of the height reserved for the illustration. |
| `GB_MAX_EVENTS` | `12` | Upper bound before the `+N altri` note. |
| `GB_SLOTS` | `5,12,18` | Hours at which the board is regenerated. |
| `GB_DISPLAY_TOKEN` | — | Required to serve. At least 24 characters. |
| `GB_ALLOW_NO_TOKEN` | `0` | Local development escape hatch. |
| `GB_BIND_HOST` | `127.0.0.1` | The image sets `0.0.0.0`; the port is not published. |
| `GB_PORT` | `8000` | |
| `GB_OUTPUT_DIR` | `./data` | PNG and state. `/data` in the container. |
| `GB_FONT_DIR` | `./assets/fonts` | |
| `GB_REQUEST_TIMEOUT` | `20` | Seconds, for both sources. |

## Client data

The calendar carries client information — addresses, notes, attendee emails.
`parse_ical` keeps four fields per event (title, start, end, all-day) and
discards the rest at the point of parsing, so nothing downstream can leak what
it never received. `Board.to_dict()` is the shape a phase-2 model payload will
take, and `tests/test_privacy.py` asserts that a feed full of client details
produces a payload containing none of them.

If you add a field to `Event`, you are moving that boundary. Do it deliberately.

## Failure behaviour

Neither source can take the board down. An unreachable calendar renders as
*Calendario non raggiungibile*, a failed weather call as `—` and a footer note.
The PNG is written atomically, so a device polling mid-render gets the previous
board rather than half a file, and a render that raises leaves the last good
PNG in place.

## The Kindle

See [kindle/README.md](kindle/README.md).

## Licence

Apache 2.0, inherited from the upstream project. The bundled
[Inter](https://github.com/rsms/inter) typeface is under the SIL Open Font
License; see `assets/fonts/OFL.txt`.
