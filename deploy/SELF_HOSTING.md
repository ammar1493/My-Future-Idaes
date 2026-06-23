# Self-hosting LiveTrain on your own server & domain

Run the **entire platform on infrastructure you control** — your VPS, your
domain, your data. No Vercel, no LiveKit Cloud, no third party. Everything below
runs as Docker containers on a single machine.

## What runs where

| Container | Role |
|-----------|------|
| `caddy`    | HTTPS reverse proxy, auto Let's Encrypt certs for your domains |
| `frontend` | The React app (served by nginx) |
| `backend`  | FastAPI API + attendance engine |
| `db`       | PostgreSQL |
| `livekit`  | **Self-hosted** LiveKit SFU (video) |
| `redis`    | LiveKit's coordination store |

## Prerequisites

- A Linux server with a **public IP** (any provider: Hetzner, DigitalOcean, AWS EC2, your own box).
- **Docker** + **Docker Compose** installed.
- A **domain you own**, with two DNS **A records** pointing at the server's IP:
  - `app.example.com`  → the platform
  - `lk.example.com`   → the LiveKit media server

## Firewall / ports to open

| Port | Proto | Why |
|------|-------|-----|
| 80, 443 | TCP | HTTP/HTTPS (Caddy, cert issuance) |
| 7881 | TCP | LiveKit media (TCP fallback) |
| 50000–50100 | UDP | LiveKit media (RTP). Widen the range for more concurrent users. |

## Steps

```bash
git clone <your-repo-url>
cd My-Future-Idaes/deploy

cp .env.prod.example .env.prod
# Edit .env.prod: set APP_DOMAIN, LIVEKIT_DOMAIN, strong passwords/secrets,
# and a matching LIVEKIT_API_KEY / LIVEKIT_API_SECRET.

# Make livekit.yaml match:
#   - keys:  <LIVEKIT_API_KEY>: <LIVEKIT_API_SECRET>
#   - webhook.api_key: <LIVEKIT_API_KEY>
#   - webhook.urls:    https://<APP_DOMAIN>/api/livekit/webhook
nano livekit.yaml

docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

Caddy will fetch TLS certificates automatically (give it a minute on first run).

### Seed an initial coordinator (optional)

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend python -m app.seed
```

Then open `https://app.example.com` and sign in. Start a session, hit **Copy
link**, and that `https://app.example.com/room/<id>` link drops anyone enrolled
straight into a live class on **your** LiveKit server — attendance recorded
automatically.

## How the pieces connect

- The browser loads the app from `https://app.example.com`; API and websocket
  calls go to the same origin and Caddy routes `/api` + `/ws` to the backend.
- For video, the backend mints a LiveKit token and the browser connects to
  `wss://lk.example.com` (Caddy → livekit:7880). Media flows over the UDP/TCP
  ports above directly to the `livekit` container.
- On join/leave, LiveKit POSTs to `…/api/livekit/webhook`; the attendance engine
  turns those into the register. All of it stays on your server.

## Notes & scaling

- **No LiveKit at all?** Leave `LIVEKIT_*` blank and the platform falls back to
  the built-in WebRTC mesh (small classes only). But for real use, keep the
  self-hosted LiveKit container — it's already wired up here.
- **More concurrent users:** widen the UDP `port_range_*` in `livekit.yaml` (and
  the matching published range in the compose file).
- **TURN / strict networks:** for users behind restrictive firewalls, enable
  LiveKit's TURN/TLS (`turn:` section in `livekit.yaml`) on port 443/5349.
- **Backups:** the `pgdata` volume holds all courses/attendance — back it up.
- **Migrations:** the app currently auto-creates tables on startup; for upgrades
  over time, add Alembic (see the root README roadmap).
