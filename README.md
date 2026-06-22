# LiveTrain — Live Online Training Platform

A platform for running **up to 100 live online courses simultaneously**, where a
single coordinator can monitor every running session from one dashboard and
**attendance is captured automatically** — no manual register, for every course
at once.

Instead of bolting onto Zoom / Teams / Meet, LiveTrain ships its own WebRTC
video rooms. Because we own the signaling, every join, leave, and heartbeat is
logged at the source, and an attendance engine derives a precise, tamper-evident
register for each session.

---

## Why a custom platform?

Automated attendance is only as good as the join/leave signal it's built on.
Third-party meeting APIs expose that signal inconsistently and with delay. By
owning the room, LiveTrain gets:

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

**Attendance pipeline:** the room websocket writes `join` / `leave` / `heartbeat`
rows to an append-only `presence_events` table. The attendance engine
(`app/core/attendance_engine.py`) replays a session's events into present-seconds
per student, divides by session length, and classifies each student as
`present` / `partial` / `absent` against configurable thresholds. It runs:

- continuously, every 60s, for all live sessions (background ticker), and
- definitively when a session ends.

The computation is **idempotent and log-derived**, so restarts, duplicate joins,
and dropped sockets never corrupt the register.

---

## Tech stack

| Layer     | Choice                                  |
|-----------|-----------------------------------------|
| Backend   | Python · FastAPI · SQLAlchemy 2         |
| Database  | PostgreSQL                              |
| Realtime  | WebSockets (signaling + dashboard)      |
| Video     | WebRTC mesh (STUN); SFU-ready           |
| Frontend  | React · Vite · React Router             |
| Deploy    | Docker Compose                          |

---

## Quick start (Docker)

```bash
docker compose up --build
# Frontend  → http://localhost:8080
# API docs  → http://localhost:8000/docs
```

Seed demo data (12 courses, all live, with enrolled students):

```bash
docker compose exec backend python -m app.seed
```

Then sign in as **coordinator@livetrain.dev / password** to see every running
course on the dashboard.

## Local development

**Backend**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # uses Postgres by default
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

## Scaling to 100 concurrent courses

- **Media:** the default WebRTC mesh suits small cohorts. For large classes,
  point `relay_to_room` (in `app/core/realtime.py`) at an SFU such as LiveKit or
  mediasoup. The attendance layer is independent of media transport.
- **Realtime fan-out:** per-process room/dashboard state lives in `RoomHub`. To
  run multiple API workers, back it with Redis pub/sub — the
  broadcast/relay interface stays the same.
- **Attendance:** computed from the event log in a single cheap pass per session;
  comfortably handles ~100 live sessions on the 60s ticker.

## Project layout

```
backend/
  app/
    api/        auth, courses, sessions, dashboard, rooms (WS)
    core/       security, deps, attendance_engine, realtime (RoomHub)
    models/     users, courses, sessions, attendance
    schemas/    Pydantic request/response models
    seed.py     demo data
  tests/        attendance engine unit tests
frontend/
  src/
    pages/      Login, Dashboard, Courses, Room (WebRTC)
    context/    AuthContext
    api/        REST + WS client
docker-compose.yml
```

## Roadmap

- [ ] SFU integration (LiveKit) for large rooms
- [ ] Redis-backed `RoomHub` for horizontal scaling
- [ ] Recurring schedules & calendar invites
- [ ] CSV / SIS export of attendance registers
- [ ] Screen share, recording, breakout rooms
- [ ] Alembic migrations (currently `create_all` on startup)
