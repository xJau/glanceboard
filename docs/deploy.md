# Deploying on the Pi

The Pi already runs Docker Compose, Caddy and a Cloudflare Tunnel. This adds one
container behind them.

## 1. Configure

On the Pi, in the repository:

```bash
cp .env.example .env
python3 -m glanceboard token     # paste the output into GB_DISPLAY_TOKEN
```

Fill in `GB_ICAL_URL` (the private feed — treat it as a password),
`GB_LAT`/`GB_LON`, and `GB_TIMEZONE`. Leave the panel size at the Paperwhite 4
default unless the device changes.

`GB_ICAL_URL_FILE=/run/secrets/ical_url` works too, if you would rather keep the
feed out of the env file.

## 2. Start it

```bash
docker compose up -d --build
docker compose logs -f glanceboard
```

The first board renders at startup. Check it without leaving the Pi:

```bash
docker compose exec glanceboard \
  python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/healthz').read())"
```

`compose.yaml` publishes no ports on purpose. If Caddy runs in a container, put
both on the same network (`edge` in the file — mark it `external: true` if Caddy
already owns it). If Caddy runs on the host instead, uncomment the
`127.0.0.1:8000:8000` mapping, which keeps the port off the LAN.

## 3. Caddy

```
glanceboard.example.com {
    reverse_proxy glanceboard:8000
}
```

Use `127.0.0.1:8000` instead of `glanceboard:8000` if Caddy is on the host.

## 4. Tunnel

In the tunnel's ingress rules, route the hostname to Caddy:

```yaml
ingress:
  - hostname: glanceboard.example.com
    service: http://caddy:80
  - service: http_status:404
```

Or add the public hostname in the Zero Trust dashboard if the tunnel is managed
remotely.

## 5. Access policy — the part that is easy to get wrong

1. **Zero Trust → Access controls → Service credentials → Service Tokens →
   Create Service Token.** Copy the Client ID and Client Secret; the secret is
   shown once. New secrets look like `cfast_…`; older 64-character hex secrets
   keep working.
2. Add `glanceboard.example.com` as a **self-hosted application**.
3. Add a policy to it:

   | Action | Rule type | Selector | Value |
   |---|---|---|---|
   | **Service Auth** | Include | Service Token | your token |

The action must be **Service Auth**. With `Allow`, Access asks for an identity
provider login, the Kindle receives an HTML login page instead of a PNG, and the
device log says `is not a PNG` — which is the single most likely way this
deployment fails.

If you also want to open the board in a browser yourself, add a *second* policy
with action `Allow` and your email. Two policies, not one with both rules.

## 6. Verify from the Mac before touching the Kindle

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://glanceboard.example.com/display
# expect 302 or 403 — Access is doing its job

curl -sS -D- -o board.png \
  -H "CF-Access-Client-Id: <CLIENT_ID>" \
  -H "CF-Access-Client-Secret: <CLIENT_SECRET>" \
  -H "Authorization: Bearer <GB_DISPLAY_TOKEN>" \
  https://glanceboard.example.com/display
# expect 200 and image/png

curl -sS \
  -H "CF-Access-Client-Id: <CLIENT_ID>" \
  -H "CF-Access-Client-Secret: <CLIENT_SECRET>" \
  -H "Authorization: Bearer <GB_DISPLAY_TOKEN>" \
  https://glanceboard.example.com/display/check
```

Then drop one of the three headers and confirm you get a `401` or an Access
redirect. Both layers should be able to refuse on their own.

## 7. Kindle

Fill in `/mnt/us/glanceboard/glanceboard.conf` with the same three values —
`BASE_URL`, `DISPLAY_TOKEN`, and the two `CF_ACCESS_*` fields — then follow
[kindle/README.md](../kindle/README.md).

## Rotating the token

`GB_DISPLAY_TOKEN` in `.env`, then `docker compose up -d`, then the same value
in the device config. The device fails closed in between: it logs the error,
keeps the board already on screen, and retries at the next wake-up.
