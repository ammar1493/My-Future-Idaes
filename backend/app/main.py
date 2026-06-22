"""LiveTrain API — entrypoint."""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api import auth, courses, dashboard, rooms, sessions
from app.config import settings
from app.core.attendance_engine import recompute_session_attendance
from app.database import Base, SessionLocal, engine
from app.models import CourseSession, SessionStatus


async def _attendance_ticker() -> None:
    """Periodically refresh attendance for all live sessions.

    Keeps the coordinator's live numbers warm and survives crashes: even if a
    session never gets a clean `end`, its attendance is continually derived
    from the event log. Cheap and scales to ~100 concurrent live rooms.
    """
    while True:
        await asyncio.sleep(60)
        db = SessionLocal()
        try:
            live = db.execute(
                select(CourseSession).where(CourseSession.status == SessionStatus.live)
            ).scalars().all()
            for session in live:
                recompute_session_attendance(db, session)
        except Exception:
            db.rollback()
        finally:
            db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    task = asyncio.create_task(_attendance_ticker())
    yield
    task.cancel()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(sessions.router)
app.include_router(dashboard.router)
app.include_router(rooms.router)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}
