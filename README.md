# NEFT ENERGIES — Live Training Platform

A platform for **NEFT ENERGIES** to run **up to 100 live online courses
simultaneously**, where a single coordinator can monitor every running session
from one dashboard and **attendance is captured automatically** — no manual
register, for every course at once.

Instead of bolting onto Zoom / Teams / Meet, the platform ships its own WebRTC
video rooms. Because we own the signaling, every join, leave, and heartbeat is
logged at the source, and an attendance engine derives a precise, tamper-evident
register for each session.

## Screenshots

| Coordinator dashboard | Courses & sessions |
|---|---|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Courses](docs/screenshots/courses.png) |

| Sign in | |
|---|---|
| ![Login](docs/screenshots/login.png) | |

The dashboard shows one coordinator watching many courses live at once, with
per-course presence bars; the register is computed automatically from join/leave
events — no manual roll call.

### Branding

The UI uses the NEFT ENERGIES palette (navy `#0B2545`, gold `#F4B41A`, green/teal
accents). The brand mark renders from a scalable SVG by default. **To use the
exact logo image, save it as `frontend/public/logo.png`** — the header and login
screen will pick it up automatically (the SVG is the fallback).

---

## Why a custom platform?

Automated attendance is only as good as the join/leave signal it's built on.
Third-party meeting APIs expose that signal inconsistently and with delay. By
owning the room, the platform gets:

- **Exact presence** — every participant's join/leave/heartbeat timestamped server-side.
- **Crash tolerance** — a student whose laptop dies is closed out at their last
  heartbeat, not credited for the whole class.
- **One coordinator, 100 rooms** — a live dashboard that updates by websocket as
  people come and go, with zero polling.

---

## Architecture

```
                    ┌─────────────────────────────┐
  Coordinator  ───► │  Dashboard (React)          │ ◄── live presence (WebSocket)
                    └─────────────┬───────────────┘
                                  │ REST + WS
                    ┌─────────────▼───────────────┐
  Students/    ───► │  FastAPI backend            │
  Instructors       │   • auth (JWT, roles)       │
   (WebRTC room)    │   • courses / enrollment    │
                    │   • sessions (live/ended)   │
                    │   • room signaling (WS)  ───┼──► PresenceEvent log (append-only)
                    │   • attendance engine    ◄──┘        │
                    └─────────────┬───────────────┘        ▼
                                  │                 AttendanceRecord (derived)
                            ┌─────▼─────┐
                            │ Postgres  │
                            └───────────┘
```

**Attendance pipeline:** every join/leave is written as an append-only row in
`presence_events`. LiveKit calls `/api/livekit/webhook` on `participant_joined` /
`participant_left`; we translate each into a presence event. No persistent socket
on our side — so the backend runs entirely on serverless (Vercel).

The attendance engine (`app/core/attendance_engine.py`) replays a
session's events into present-seconds per student, divides by session length,
and classifies each as `present` / `partial` / `absent` against configurable
thresholds — **idempotent and log-derived**, so restarts, duplicate joins, and
dropped connections never corrupt the register. It recomputes on each leave
webhook, on session end, and on demand (`?recompute=true`).

---

## Tech stack

| Layer     | Choice                                  |
|-----------|-----------------------------------------|
| Backend   | Python · FastAPI · SQLAlchemy 2         |
| Database  | Vercel Postgres                         |
| Realtime  | LiveKit webhooks · dashboard polling    |
| Video     | LiveKit Cloud (managed SFU)             |
| Frontend  | React · Vite · React Router             |
| Deploy    | Vercel (frontend + serverless API)      |

---

## Local development

**Backend**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # set DATABASE_URL (Postgres; or sqlite:///./dev.db for a quick local run)
uvicorn app.main:app --reload
python -m app.seed                   # optional demo data
pytest                               # attendance engine tests
```

**Frontend**
```bash
cd frontend
npm install
npm run dev                          # http://localhost:5173 (proxies API to :8000)
```

---

## Roles

| Role          | Can do                                                         |
|---------------|----------------------------------------------------------------|
| `admin`       | Everything                                                     |
| `coordinator` | The live dashboard across all courses; manage courses/sessions |
| `instructor`  | Manage and run their own courses/sessions                      |
| `student`     | Join live rooms (attendance captured automatically)            |

---

## Key API endpoints

| Method | Path                               | Purpose                              |
|--------|------------------------------------|--------------------------------------|
| POST   | `/api/auth/register` · `/login`    | Accounts & JWT                       |
| GET    | `/api/courses`                     | List / create courses                |
| POST   | `/api/sessions/{id}/start` · `/end`| Open / close a live room             |
| GET    | `/api/sessions/{id}/attendance`    | Per-student register (`?recompute`)  |
| GET    | `/api/dashboard/summary`           | Snapshot of all running courses      |
| WS     | `/api/dashboard/live`              | Live presence push to coordinator    |
| WS     | `/ws/rooms/{room_id}?token=…`      | Join a room (WebRTC + attendance)    |

---

## Deploy on Vercel (recommended — no server to run)

> **Full click-by-click runbook: [`DEPLOY.md`](DEPLOY.md)** — includes a ready
> first login (auto-created coordinator) and student self-signup, so it works
> the moment it's deployed.

Everything **you operate runs on Vercel**: the frontend, the API (Python
serverless functions), and the database (**Vercel Postgres**). There is no
server to provision or maintain.

> **One honest caveat about live video.** Vercel's serverless functions can't
> host a real-time video media server (an SFU needs persistent UDP/WebSocket
> connections that serverless doesn't provide). So the *video transport* uses
> **LiveKit Cloud** — a fully managed service, nothing for you to run or
> maintain (just like Vercel). Your app, data, and attendance logic stay 100% on
> Vercel; LiveKit Cloud only carries the audio/video streams. This is the only
> way to have custom in-app live video without running your own server.

You'll need: a **Vercel** account, **Vercel Postgres** (one click in the Vercel
dashboard), and a free **LiveKit Cloud** project.

1. **Push this repo to GitHub** (Vercel deploys from a git repo).

2. **LiveKit Cloud** → create a project. Copy the **WSS URL**, **API key**, and
   **API secret**. Under the project's **Webhooks**, add:
   `https://<your-backend-host>/api/livekit/webhook`

3. **Database** → in the Vercel dashboard, **Storage → Create → Postgres**, then
   copy its connection string (prefix it as `postgresql+psycopg://…`).

4. **Backend → Vercel** (new project, root directory = `backend/`). Env vars:
   ```
   DATABASE_URL=postgresql+psycopg://…   (Vercel Postgres)
   SECRET_KEY=<long random>
   LIVEKIT_URL=wss://<your>.livekit.cloud
   LIVEKIT_API_KEY=…
   LIVEKIT_API_SECRET=…
   CORS_ORIGINS=https://<your-frontend>.vercel.app
   ```
   `backend/vercel.json` serves the FastAPI app as a Python serverless function.

5. **Frontend → Vercel** (new project, root directory = `frontend/`). Env var:
   ```
   VITE_API_BASE=https://<your-backend>.vercel.app
   ```

6. Open the frontend URL, sign in, start a session, and hit **Copy link** — that
   shareable `/room/<id>` link drops anyone enrolled straight into the live
   LiveKit room, with attendance captured automatically.

## Scaling to 100 concurrent courses

- **Media:** LiveKit Cloud is a production SFU and scales to large classes out of
  the box. The attendance layer is independent of media transport.
- **Realtime:** live counts are derived from the presence-event log in the DB, so
  the dashboard scales horizontally with no shared in-memory state — any
  serverless instance can serve it.
- **Attendance:** computed from the event log in a single cheap pass per session;
  recomputed on each LiveKit leave webhook and on session end.

## Project layout

```
backend/
  app/
    api/        auth, courses, sessions, dashboard, livekit_rooms, meta
    core/       security, deps, attendance_engine, livekit
    models/     users, courses, sessions, attendance
    schemas/    Pydantic request/response models
    seed.py     demo data
  api/index.py  Vercel serverless entry
  vercel.json   Vercel Python function config
  tests/        attendance engine unit tests
frontend/
  public/       favicon, logo.png (your brand asset)
  src/
    pages/      Login, Dashboard, Courses, Room (LiveKit)
    components/  Logo
    context/    AuthContext
    api/        REST client
  vercel.json   Vite SPA config
```

## Roadmap

- [x] SFU integration (LiveKit) for large rooms
- [x] Generated shareable join links
- [x] Vercel-ready serverless deployment
- [ ] Recurring schedules & calendar invites
- [ ] CSV / SIS export of attendance registers
- [ ] Recording & breakout rooms (LiveKit Egress)
- [ ] Alembic migrations (currently `create_all` on startup)
