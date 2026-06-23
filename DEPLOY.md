# Deploy NEFT ENERGIES to Vercel — step by step

Everything you operate runs on **Vercel** (web app + API + Postgres). Live video
is carried by **LiveKit Cloud** (a managed service — nothing to run; serverless
can't host a media server). No other servers.

You'll do this entirely in browser dashboards — no command line needed.

---

## 0. Accounts (free tiers are fine)
- GitHub (this repo is already pushed)
- Vercel — https://vercel.com  (sign in with GitHub)
- LiveKit Cloud — https://cloud.livekit.io

---

## 1. LiveKit Cloud
1. Create a project.
2. From the project **Settings → Keys**, copy:
   - **WebSocket URL** → looks like `wss://yourproject.livekit.cloud`
   - **API Key**
   - **API Secret**
3. Leave a tab open — you'll add the webhook in step 5 once the backend URL exists.

---

## 2. Database — Vercel Postgres
1. In Vercel: **Storage → Create Database → Postgres** → create it.
2. Open the DB → **.env.local / Connection** tab → copy the connection string.
3. You'll paste it as `DATABASE_URL` in step 3, **rewritten** to use the psycopg
   driver and SSL:
   ```
   postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require
   ```
   (Take the `postgres://…` Vercel gives you and change the scheme to
   `postgresql+psycopg://`, keep `?sslmode=require`.)

---

## 3. Backend project (FastAPI on Vercel)
1. Vercel → **Add New → Project** → import this GitHub repo.
2. **Root Directory: `backend`**  ← important.
3. Framework preset: **Other**. Leave build/output empty (vercel.json handles it).
4. Add **Environment Variables**:

   | Name | Value |
   |------|-------|
   | `DATABASE_URL` | your `postgresql+psycopg://…?sslmode=require` |
   | `SECRET_KEY` | `306ac5514fadfbb3ce22b757467d29c5f251f78b0c6cbf35f1e2984f72d51fb2` (or your own) |
   | `LIVEKIT_URL` | `wss://yourproject.livekit.cloud` |
   | `LIVEKIT_API_KEY` | from LiveKit |
   | `LIVEKIT_API_SECRET` | from LiveKit |
   | `BOOTSTRAP_COORDINATOR_EMAIL` | the email you'll log in with |
   | `BOOTSTRAP_COORDINATOR_PASSWORD` | a strong password |
   | `CORS_ORIGINS` | (fill after step 4 with the frontend URL) |

5. **Deploy.** Note the backend URL, e.g. `https://neft-backend.vercel.app`.
   Test it: visiting `https://neft-backend.vercel.app/health` should return
   `{"status":"ok","app":"NEFT Energies"}`.

---

## 4. Frontend project (React on Vercel)
1. Vercel → **Add New → Project** → import the **same** repo again.
2. **Root Directory: `frontend`**.
3. Framework preset: **Vite** (auto-detected).
4. Add Environment Variable:

   | Name | Value |
   |------|-------|
   | `VITE_API_BASE` | your backend URL from step 3, e.g. `https://neft-backend.vercel.app` |

5. **Deploy.** Note the frontend URL, e.g. `https://neft.vercel.app`.

---

## 5. Wire the two together
1. Back in the **backend** project → Settings → Environment Variables → set
   `CORS_ORIGINS` = your frontend URL (e.g. `https://neft.vercel.app`) → **Redeploy**.
2. In **LiveKit Cloud** → project **Settings → Webhooks** → add:
   `https://neft-backend.vercel.app/api/livekit/webhook`
   (This is what records attendance automatically.)

---

## 6. Use it 🎉
1. Open the frontend URL and sign in with your
   `BOOTSTRAP_COORDINATOR_EMAIL` / `BOOTSTRAP_COORDINATOR_PASSWORD`.
2. **Courses** → add a course → **+ Session now** → **Start** → **Copy link**.
3. Share that link with trainees. They click it, **Create an account** (student
   signup), and land straight in the live class.
4. Watch the **Dashboard**: every running course with live headcounts; attendance
   is recorded automatically and viewable per session.

### Optional: use your exact logo
Add your logo image to the repo at `frontend/public/logo.png` and redeploy — the
header and login will use it automatically.

### Custom domain
In either Vercel project → **Settings → Domains** → add your domain (e.g.
`training.neftenergies.com` for the frontend). Update `CORS_ORIGINS` /
`VITE_API_BASE` to match, then redeploy.

---

## Troubleshooting (most common issues)

- **`/health` errors or DB connection fails** → `DATABASE_URL` must start with
  `postgresql+psycopg://` (not `postgres://`) and end with `?sslmode=require`.
- **Can't log in as coordinator** → the coordinator is created on a cold start
  *after* `BOOTSTRAP_COORDINATOR_EMAIL` / `_PASSWORD` exist. If you added them
  after the first deploy, **Redeploy** the backend, then try again.
- **Frontend shows CORS / network errors** → `CORS_ORIGINS` (backend) must be the
  exact frontend URL — `https://…`, **no trailing slash**. Redeploy backend after
  changing it.
- **Frontend calls the wrong API / localhost** → `VITE_API_BASE` is baked in at
  **build time**. After changing it you must **Redeploy the frontend**.
- **API returns 404 for `/api/...`** → the backend project's **Root Directory**
  must be `backend` (and the frontend's must be `frontend`).
- **Video won't connect / attendance stays 0** → check `LIVEKIT_URL` (starts with
  `wss://`), key/secret, and that the LiveKit **webhook** points to
  `https://<backend>/api/livekit/webhook`. Attendance updates as students
  join/leave the LiveKit room.
