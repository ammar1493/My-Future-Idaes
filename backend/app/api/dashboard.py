"""Coordinator dashboard: a single live view across all running courses."""
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import require_coordinator
from app.core.realtime import hub
from app.database import SessionLocal, get_db
from app.models import (
    Course,
    CourseSession,
    Enrollment,
    PresenceEvent,
    PresenceEventType,
    SessionStatus,
    User,
)
from app.schemas import DashboardSummary, LiveCourseTile

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _live_counts_from_events(db: Session, session_ids: list[int]) -> dict[str, int]:
    """Count who is currently in each session's room, derived from the event log.

    A user is "in the room" when their most recent presence event is not a
    `leave`. This is DB-only (no in-memory state), so it works on serverless and
    is identical whether media flows over LiveKit webhooks or the built-in mesh.
    Returns {room_id: count}.
    """
    if not session_ids:
        return {}
    # Latest event timestamp per (session, user).
    latest = (
        select(
            PresenceEvent.session_id,
            PresenceEvent.user_id,
            func.max(PresenceEvent.at).label("max_at"),
        )
        .where(PresenceEvent.session_id.in_(session_ids))
        .group_by(PresenceEvent.session_id, PresenceEvent.user_id)
        .subquery()
    )
    rows = db.execute(
        select(PresenceEvent.session_id, PresenceEvent.user_id, PresenceEvent.event_type)
        .join(
            latest,
            (PresenceEvent.session_id == latest.c.session_id)
            & (PresenceEvent.user_id == latest.c.user_id)
            & (PresenceEvent.at == latest.c.max_at),
        )
    ).all()

    by_session: dict[int, int] = {}
    for session_id, _user_id, event_type in rows:
        if event_type != PresenceEventType.leave:
            by_session[session_id] = by_session.get(session_id, 0) + 1
    # Map session_id -> room_id is resolved by the caller; here return per session id.
    return by_session


def _build_summary(db: Session) -> DashboardSummary:
    sessions = db.execute(
        select(CourseSession, Course)
        .join(Course, Course.id == CourseSession.course_id)
        .where(CourseSession.status == SessionStatus.live)
        .order_by(CourseSession.scheduled_start)
    ).all()

    # Enrollment counts in one grouped query (avoids N+1 across 100 courses).
    enroll_rows = db.execute(
        select(Enrollment.course_id, func.count(Enrollment.id)).group_by(Enrollment.course_id)
    ).all()
    enrolled_by_course = {cid: cnt for cid, cnt in enroll_rows}

    live_by_session = _live_counts_from_events(db, [s.id for s, _ in sessions])

    tiles: list[LiveCourseTile] = []
    total_live_participants = 0
    for session, course in sessions:
        live_now = live_by_session.get(session.id, 0)
        total_live_participants += live_now
        tiles.append(
            LiveCourseTile(
                session_id=session.id,
                course_id=course.id,
                course_title=course.title,
                session_title=session.title,
                room_id=session.room_id,
                status=session.status,
                enrolled=enrolled_by_course.get(course.id, 0),
                live_now=live_now,
                scheduled_start=session.scheduled_start,
                scheduled_end=session.scheduled_end,
            )
        )

    total_courses = db.execute(select(func.count(Course.id))).scalar_one()
    return DashboardSummary(
        total_live_sessions=len(tiles),
        total_participants_live=total_live_participants,
        total_courses=total_courses,
        tiles=tiles,
    )


@router.get("/summary", response_model=DashboardSummary)
def summary(db: Session = Depends(get_db), _: User = Depends(require_coordinator)):
    """Snapshot of every running course for the coordinator."""
    return _build_summary(db)


@router.websocket("/live")
async def dashboard_live(ws: WebSocket):
    """Push live presence updates to the coordinator as they happen."""
    await ws.accept()
    await hub.subscribe_dashboard(ws)
    # Send an initial snapshot immediately on connect.
    db = SessionLocal()
    try:
        await ws.send_json({"type": "snapshot", "data": _build_summary(db).model_dump(mode="json")})
    finally:
        db.close()
    try:
        while True:
            await ws.receive_text()  # keep-alive; client may ping
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unsubscribe_dashboard(ws)
