"""Live session scheduling and lifecycle (start / end)."""
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.attendance_engine import recompute_session_attendance
from app.core.deps import get_current_user, require_staff
from app.database import get_db
from app.models import Course, CourseSession, SessionStatus, User
from app.schemas import AttendanceOut, SessionCreate, SessionOut

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionOut])
def list_sessions(
    status: SessionStatus | None = None,
    course_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(CourseSession)
    if status:
        stmt = stmt.where(CourseSession.status == status)
    if course_id:
        stmt = stmt.where(CourseSession.course_id == course_id)
    return db.execute(stmt.order_by(CourseSession.scheduled_start)).scalars().all()


@router.post("", response_model=SessionOut)
def create_session(
    payload: SessionCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    course = db.get(Course, payload.course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    session = CourseSession(
        course_id=payload.course_id,
        title=payload.title or course.title,
        room_id=secrets.token_urlsafe(9),
        scheduled_start=payload.scheduled_start,
        scheduled_end=payload.scheduled_end,
        status=SessionStatus.scheduled,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.post("/{session_id}/start", response_model=SessionOut)
def start_session(session_id: int, db: Session = Depends(get_db), _: User = Depends(require_staff)):
    session = db.get(CourseSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.status = SessionStatus.live
    session.actual_start = datetime.now(timezone.utc)
    db.commit()
    db.refresh(session)
    return session


@router.post("/{session_id}/end", response_model=SessionOut)
def end_session(session_id: int, db: Session = Depends(get_db), _: User = Depends(require_staff)):
    session = db.get(CourseSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.status = SessionStatus.ended
    session.actual_end = datetime.now(timezone.utc)
    db.commit()
    # Finalize attendance from the event log.
    recompute_session_attendance(db, session)
    db.refresh(session)
    return session


@router.get("/{session_id}", response_model=SessionOut)
def get_session(session_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    session = db.get(CourseSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/{session_id}/attendance", response_model=list[AttendanceOut])
def session_attendance(
    session_id: int,
    recompute: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    session = db.get(CourseSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if recompute:
        return recompute_session_attendance(db, session)
    return session.attendance_records
