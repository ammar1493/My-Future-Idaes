"""LiveKit join tokens + webhook-driven attendance.

Flow:
  1. A user requests a join token for a live session -> we return the LiveKit
     URL and a signed token (identity = user id, room = session.room_id).
  2. The client connects to LiveKit directly for audio/video.
  3. LiveKit calls our webhook on join/leave -> we append PresenceEvent rows and
     recompute attendance on leave. No persistent socket on our side, so this
     runs happily on serverless (Vercel).
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.attendance_engine import recompute_session_attendance
from app.core.deps import get_current_user
from app.core.livekit import create_join_token, webhook_receiver
from app.database import get_db
from app.models import (
    CourseSession,
    PresenceEvent,
    PresenceEventType,
    SessionStatus,
    User,
)

router = APIRouter(tags=["livekit"])


@router.post("/api/rooms/{room_id}/join-token")
def join_token(room_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Mint a LiveKit token for the room behind a shared join link."""
    if not settings.livekit_enabled:
        raise HTTPException(status_code=400, detail="LiveKit is not configured")
    session = db.execute(
        select(CourseSession).where(CourseSession.room_id == room_id)
    ).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Room not found")
    if session.status != SessionStatus.live:
        raise HTTPException(status_code=403, detail="Session is not live")
    token = create_join_token(session.room_id, user.id, user.full_name)
    return {"url": settings.livekit_url, "token": token, "room": session.room_id}


def _log(db: Session, session_id: int, user_id: int, kind: PresenceEventType) -> None:
    db.add(
        PresenceEvent(
            session_id=session_id,
            user_id=user_id,
            event_type=kind,
            at=datetime.now(timezone.utc),
        )
    )
    db.commit()


@router.post("/api/livekit/webhook")
async def livekit_webhook(request: Request, db: Session = Depends(get_db)):
    """Receive LiveKit room events and translate them into presence events."""
    if not settings.livekit_enabled:
        raise HTTPException(status_code=400, detail="LiveKit is not configured")

    body = (await request.body()).decode("utf-8")
    auth = request.headers.get("Authorization", "")
    try:
        event = webhook_receiver().receive(body, auth)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    room_name = getattr(event.room, "name", None) if event.room else None
    identity = getattr(event.participant, "identity", None) if event.participant else None
    if not room_name or identity is None:
        return {"ok": True}  # events we don't care about (e.g. track published)

    session = db.execute(
        select(CourseSession).where(CourseSession.room_id == room_name)
    ).scalar_one_or_none()
    if not session:
        return {"ok": True}

    try:
        user_id = int(identity)
    except ValueError:
        return {"ok": True}

    if event.event == "participant_joined":
        _log(db, session.id, user_id, PresenceEventType.join)
    elif event.event == "participant_left":
        _log(db, session.id, user_id, PresenceEventType.leave)
        recompute_session_attendance(db, session)

    return {"ok": True}
