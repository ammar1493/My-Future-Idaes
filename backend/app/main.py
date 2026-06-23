"""NEFT Energies — Live Training API entrypoint (Vercel serverless)."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, courses, dashboard, livekit_rooms, meta, sessions
from app.config import settings
from app.startup import init

# Ensure schema + bootstrap coordinator at import (serverless cold start).
# Attendance is recomputed on each LiveKit leave webhook and on session end, so
# no background worker is needed.
init()

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router)
app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(sessions.router)
app.include_router(dashboard.router)
app.include_router(livekit_rooms.router)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}
