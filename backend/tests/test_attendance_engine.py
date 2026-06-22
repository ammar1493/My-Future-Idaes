"""Unit tests for the attendance engine's pure interval math."""
from datetime import datetime, timedelta, timezone

from app.core.attendance_engine import classify, compute_present_seconds
from app.models import AttendanceStatus, PresenceEvent, PresenceEventType

T0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)


def ev(kind: PresenceEventType, minutes: float) -> PresenceEvent:
    return PresenceEvent(event_type=kind, at=T0 + timedelta(minutes=minutes))


def test_clean_join_leave():
    events = [ev(PresenceEventType.join, 0), ev(PresenceEventType.leave, 30)]
    seconds, first, last = compute_present_seconds(events, T0 + timedelta(minutes=60), 30)
    assert seconds == 30 * 60
    assert first == T0
    assert last == T0 + timedelta(minutes=30)


def test_rejoin_accumulates():
    events = [
        ev(PresenceEventType.join, 0),
        ev(PresenceEventType.leave, 10),
        ev(PresenceEventType.join, 20),
        ev(PresenceEventType.leave, 35),
    ]
    seconds, _, _ = compute_present_seconds(events, T0 + timedelta(minutes=60), 30)
    assert seconds == (10 + 15) * 60


def test_crash_without_leave_capped_by_heartbeat():
    # Joined, two heartbeats, then vanished. Should count to last heartbeat + window.
    events = [
        ev(PresenceEventType.join, 0),
        ev(PresenceEventType.heartbeat, 5),
        ev(PresenceEventType.heartbeat, 10),
    ]
    seconds, _, _ = compute_present_seconds(events, T0 + timedelta(minutes=60), 30)
    # last heartbeat at 10min + 30s window = 10.5 min
    assert seconds == int(10.5 * 60)


def test_open_interval_capped_at_session_end():
    events = [ev(PresenceEventType.join, 0), ev(PresenceEventType.heartbeat, 59)]
    seconds, _, _ = compute_present_seconds(events, T0 + timedelta(minutes=60), 30)
    # 59min + 30s = 59.5 < 60min end, so 59.5min
    assert seconds == int(59.5 * 60)


def test_classification_thresholds():
    assert classify(0.9, 0.75, 0.25) == AttendanceStatus.present
    assert classify(0.5, 0.75, 0.25) == AttendanceStatus.partial
    assert classify(0.1, 0.75, 0.25) == AttendanceStatus.absent
