"""Attendance engine.

Turns the append-only stream of `PresenceEvent` rows into a per-student
`AttendanceRecord` for a session. Designed to be:

* Idempotent  - recomputing always yields the same result.
* Crash-safe   - works purely from the event log, so a dropped websocket,
                 server restart, or duplicate join is handled gracefully.
* Scalable     - one cheap pass over a session's events; can run for all 100
                 live sessions on a schedule without contention.

Presence model
--------------
A student is "present" during the interval [join, leave]. Because clients can
crash without sending a clean `leave`, we also accept periodic `heartbeat`
events: an open interval is implicitly extended to the last heartbeat plus one
heartbeat window, and is closed at session end if never terminated.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    AttendanceRecord,
    AttendanceStatus,
    CourseSession,
    PresenceEvent,
    PresenceEventType,
)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def compute_present_seconds(
    events: list[PresenceEvent],
    session_end: datetime,
    heartbeat_window: int,
) -> tuple[int, datetime | None, datetime | None]:
    """Collapse one user's events into total present seconds.

    Returns (seconds_present, first_joined_at, last_left_at).
    """
    ordered = sorted(events, key=lambda e: _aware(e.at))
    total = 0.0
    open_since: datetime | None = None
    last_seen: datetime | None = None
    first_join: datetime | None = None
    last_leave: datetime | None = None
    hb = timedelta(seconds=heartbeat_window)

    def close(at: datetime) -> None:
        nonlocal total, open_since, last_leave
        if open_since is not None:
            total += max(0.0, (_aware(at) - open_since).total_seconds())
            last_leave = _aware(at)
            open_since = None

    for ev in ordered:
        at = _aware(ev.at)
        if ev.event_type == PresenceEventType.join:
            if open_since is None:
                open_since = at
            if first_join is None:
                first_join = at
            last_seen = at
        elif ev.event_type == PresenceEventType.heartbeat:
            if open_since is None:  # heartbeat without a join — treat as a join
                open_since = at
                if first_join is None:
                    first_join = at
            last_seen = at
        elif ev.event_type == PresenceEventType.leave:
            close(at)
            last_seen = at

    # Interval still open at the end of processing: a client that never sent a
    # clean leave. Extend to last heartbeat + one window, capped at session end.
    if open_since is not None:
        implied_end = (last_seen + hb) if last_seen else open_since
        close(min(implied_end, _aware(session_end)))

    return int(round(total)), first_join, last_leave


def classify(ratio: float, present_threshold: float, partial_threshold: float) -> AttendanceStatus:
    if ratio >= present_threshold:
        return AttendanceStatus.present
    if ratio >= partial_threshold:
        return AttendanceStatus.partial
    return AttendanceStatus.absent


def session_duration_seconds(session: CourseSession) -> int:
    start = session.actual_start or session.scheduled_start
    end = session.actual_end or session.scheduled_end
    start, end = _aware(start), _aware(end)
    return max(1, int((end - start).total_seconds()))


def recompute_session_attendance(db: Session, session: CourseSession) -> list[AttendanceRecord]:
    """(Re)compute attendance for every participant who has any event."""
    course = session.course
    present_threshold = (
        course.present_threshold
        if course and course.present_threshold is not None
        else settings.attendance_present_threshold
    )
    partial_threshold = (
        course.partial_threshold
        if course and course.partial_threshold is not None
        else settings.attendance_partial_threshold
    )

    events = db.execute(
        select(PresenceEvent).where(PresenceEvent.session_id == session.id)
    ).scalars().all()

    by_user: dict[int, list[PresenceEvent]] = {}
    for ev in events:
        by_user.setdefault(ev.user_id, []).append(ev)

    duration = session_duration_seconds(session)
    session_end = session.actual_end or session.scheduled_end

    existing = {
        r.user_id: r
        for r in db.execute(
            select(AttendanceRecord).where(AttendanceRecord.session_id == session.id)
        ).scalars().all()
    }

    records: list[AttendanceRecord] = []
    for user_id, user_events in by_user.items():
        seconds, first_join, last_leave = compute_present_seconds(
            user_events, session_end, settings.presence_heartbeat_seconds
        )
        ratio = min(1.0, seconds / duration)
        status = classify(ratio, present_threshold, partial_threshold)

        record = existing.get(user_id) or AttendanceRecord(session_id=session.id, user_id=user_id)
        record.seconds_present = seconds
        record.attendance_ratio = round(ratio, 4)
        record.status = status
        record.first_joined_at = first_join
        record.last_left_at = last_leave
        if record.id is None:
            db.add(record)
        records.append(record)

    db.commit()
    return records
