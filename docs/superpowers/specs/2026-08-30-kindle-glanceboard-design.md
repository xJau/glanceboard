# Glanceboard for Kindle — phase 1 design

Date: 2026-08-30
Status: implemented

## Problem

Run a fork of google-gemini/glanceboard on a jailbroken Kindle Paperwhite
instead of a 6-colour Waveshare frame: landscape, 16 grays, native resolution.
Development happens on a Mac, deployment on a Raspberry Pi already running
Docker Compose and Caddy behind a Cloudflare Tunnel, and the same code has to
run unchanged in both places.

Phase 1 generates no images and calls no models: iCal parsing, Open-Meteo
weather, a deterministic PIL layout, and a PNG endpoint the Kindle can fetch.

## Constraints

1. The deterministic renderer stays afterwards as the fallback when phase-2 AI
   generation fails. It has to be designed to last, not to be replaced.
2. Calendar events contain client data. Only title and time may reach anything
   that will become a model payload.
3. Phase 2 will be an HTTP call to an API with handled errors and retries — not
   an assistant CLI invoked from the scheduler.
4. Upstream serves its API key from an unauthenticated `GET /api/config` and
   binds `0.0.0.0`. Both are fixed here.
5. Paths must be configurable; nothing may assume an environment.
6. A CLI must regenerate the PNG locally without starting the server.

## Decisions

### Fork strategy: strip to a lean core

Deleted `web/`, `functions/`, `firmware/`, `glanceboard_ais/`, `pi/`, the
Firebase configuration, the Gmail integration and the dashboard. Rewrote the
server as a small package. Only the iCal and Open-Meteo logic survived, rewritten.

*Why:* less surface, fewer holes, and a codebase small enough to iterate on. The
alternative — a parallel module beside an intact upstream — keeps rebasing easy
but carries an unauthenticated dashboard and a dead Gemini pipeline forever.

### Rendering: card compositor, text always drawn by PIL

The canvas is split into declared regions — ribbon, agenda card, illustration
panel, weather card, footer caption. The deterministic renderer draws all the
text, always. Phase 2 fills the illustration panel and nothing else.

*Why:* appointment times and client names are never redrawn by a model, so they
cannot be hallucinated, and the payload never needs to contain them for layout
purposes. The fallback is not a second code path that rots between failures —
it is the path that runs every day, minus one region.

Rejected: two whole-image renderers (upstream's model), where the fallback
diverges visually and is only exercised when something is already broken;
HTML-to-image via headless Chromium, which is a heavy dependency that renders
differently on ARM.

### Landscape composition, rotated at the last moment

The board is composed at 1448×1072 and rotated a quarter turn when it is
written. *Why:* the panel is physically 1072×1448, and rotating once, in one
place, beats every consumer having to know which way up the device is lying.
`GB_ROTATE` covers both ways of standing it; `--upright` skips the turn while
iterating on a desk.

Landscape is short, so the composition puts the agenda in a full-height column
on the left and stacks the illustration panel and the weather card on the right.
An earlier arrangement — weather under the agenda — cost the list a fifth of its
height and started dropping appointments on an ordinary day.

### Cozy, in the register of the original

The original is a storybook illustration: a ribbon headline, a bulleted list, a
rounded weather chip in the corner, a mount-board frame. The deterministic
renderer cannot draw a picture, but it can hold that register — Nunito's rounded
terminals, cards on an off-white page, a dotted rule, weather drawn as outline
glyphs rather than set as emoji (which arrive as colour bitmaps and quantize to
a smudge). Every tone is a multiple of 17, so the palette already sits on the
panel's 16-level grid and quantization never shifts a fill.

### The parser is the privacy boundary

`parse_ical` returns `Event(title, start, end, all_day)`. `location`,
`description`, `attendee`, `organizer` and `uid` are dropped inside the parser
and do not exist downstream. `Board.to_dict()` is the shape a phase-2 payload
takes, and is correct by construction rather than by a filter someone must
remember to call. `tests/test_privacy.py` feeds in a calendar full of client
details and asserts none of them reach the payload.

### Exposure: Cloudflare Access service token, plus an independent server token

Uvicorn binds `127.0.0.1` (`0.0.0.0` inside the container, whose port is never
published). Caddy proxies; the Cloudflare Tunnel exposes; an Access policy with
a service token authenticates the device.

The server additionally requires its own bearer token and refuses to start
without one at least 24 characters long. *Why:* Access is an outer door on a
path we do not control. If it is misconfigured, disabled, or the container is
reached over the LAN, the token is what still refuses. The known risk is TLS on
old Kindle firmware, hence a `CA_BUNDLE` option in the device config.

### Scheduling: fixed slots, and the server owns the clock

The board regenerates at `GB_SLOTS` hours, and once at startup if the stored
board is not from today. `/display/check` returns `now_epoch` and
`next_refresh_epoch`; the device sleeps for their difference plus a grace
period.

*Why:* a Kindle keeps its clock in UTC, drifts while suspended, and knows
nothing about the server's timezone or daylight saving. Subtracting two numbers
the server sent cannot desynchronise.

### Italian labels and a vendored font

Weekday and month names come from explicit tables, not the system locale, and
Inter is committed to `assets/fonts/`. *Why:* a Mac and a Debian container carry
different fonts and locales, and the layout being iterated on locally has to be
the layout that reaches the device.

## Structure

```
glanceboard/
  models.py         Event, Weather, Board — the only calendar representation
  config.py         Settings from the environment, GB_*_FILE for secrets
  calendar_feed.py  fetch + parse iCal; the privacy boundary
  weather.py        Open-Meteo daily min/max
  schedule.py       next slot
  pipeline.py       sources → Board → PNG, atomic writes, change detection
  render/
    theme.py        fonts, tones, Italian date vocabulary
    layout.py       geometry as fractions of the canvas
    icons.py        weather glyphs, drawn rather than set
    board.py        drawing, adaptive row density, wrapping
    grayscale.py    16-level quantization
  server.py         /display, /display/check, /healthz
  cli.py            render / serve / token
```

Fetching is separated from parsing in both sources so tests run offline against
fixtures, and so the CLI can render from a saved `.ics`.

## Behaviour under failure

| Failure | Result |
|---|---|
| Calendar unreachable or malformed | `calendar_ok=False`, agenda shows a note |
| Weather unreachable | `weather_ok=False`, temperatures `—`, footer note |
| Render raises | Previous PNG stays; no partial file |
| Too many events | Rows compact (spacing, then type size) before any event is dropped; then *e altri N appuntamenti* |
| Device offline at a slot | Next wake-up fetches the current board |

## Testing

97 tests, no network. Fixtures: a sample `.ics` carrying deliberate client data
with an all-day event, a recurrence and an over-long title; a recorded
Open-Meteo response. Coverage includes recurrence expansion, UTC→local
conversion, the privacy assertions, panel fit (≤16 grays, all multiples of 17),
render determinism, that nothing is drawn into the reserved illustration panel,
that every theme tone already sits on the 16-level grid, the rotation applied on
the way out, atomic-write behaviour, and every authentication path including the
absence of a config endpoint.

## Phase 2, and what this design already owes it

- `Board.to_dict()` is the payload; it is already safe.
- The illustration panel already has coordinates.
- Generation becomes a step in `pipeline.generate` between building the board
  and rendering it; a failure means the band stays empty and the board still
  ships.
- The HTTP call gets its own module, with a timeout, bounded retries and an
  error type the pipeline can ignore. No CLI invocation from the scheduler.
