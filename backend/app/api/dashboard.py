"""Coordinator dashboard: a single live view across all running courses."""
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import require_coordinator
from app.core.realtime import hub
from app.database import SessionLocal, get_db
from app.models import Course, CourseSession, Enrollment, SessionStatus, User
from app.schemas import DashboardSummary, LiveCourseTile

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _build_summary(db: Session) -> DashboardSummary:
    live_counts = hub.live_room_counts()

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

    tiles: list[LiveCourseTile] = []
    total_live_participants = 0
    for session, course in sessions:
        live_now = live_counts.get(session.room_id, 0)
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
