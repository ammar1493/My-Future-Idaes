"""One-time initialization run at app import.

On serverless (Vercel) the ASGI lifespan isn't reliably invoked, so we ensure
the schema exists and bootstrap an initial coordinator here, at module import —
idempotent and safe to run on every cold start.

Set these env vars in Vercel so you can log in immediately after deploy:
  BOOTSTRAP_COORDINATOR_EMAIL
  BOOTSTRAP_COORDINATOR_PASSWORD
  BOOTSTRAP_COORDINATOR_NAME   (optional)
"""
import os

from sqlalchemy import select

from app.core.security import hash_password
from app.database import Base, SessionLocal, engine
from app.models import User, UserRole


def init() -> None:
    Base.metadata.create_all(bind=engine)
    _bootstrap_coordinator()


def _bootstrap_coordinator() -> None:
    email = os.environ.get("BOOTSTRAP_COORDINATOR_EMAIL")
    password = os.environ.get("BOOTSTRAP_COORDINATOR_PASSWORD")
    if not (email and password):
        return
    db = SessionLocal()
    try:
        exists = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if exists:
            return
        db.add(
            User(
                email=email,
                full_name=os.environ.get("BOOTSTRAP_COORDINATOR_NAME", "Coordinator"),
                hashed_password=hash_password(password),
                role=UserRole.coordinator,
            )
        )
        db.commit()
    except Exception:
        # Never let bootstrap crash cold start (e.g. transient race on first deploy).
        db.rollback()
    finally:
        db.close()
