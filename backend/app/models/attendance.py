"""Presence events (raw) and computed attendance records (derived)."""
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PresenceEventType(str, enum.Enum):
    join = "join"
    leave = "leave"
    heartbeat = "heartbeat"


class PresenceEvent(Base):
    """Append-only log of a participant joining/leaving a live room.

    The attendance engine replays these to compute total time present.
    """

    __tablename__ = "presence_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("course_sessions.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    event_type: Mapped[PresenceEventType] = mapped_column(Enum(PresenceEventType))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session = relationship("CourseSession", back_populates="presence_events")


class AttendanceStatus(str, enum.Enum):
    present = "present"
    partial = "partial"
    absent = "absent"


class AttendanceRecord(Base):
    """Derived, per-(session, student) attendance summary."""

    __tablename__ = "attendance_records"
    __table_args__ = (UniqueConstraint("session_id", "user_id", name="uq_session_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("course_sessions.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    seconds_present: Mapped[int] = mapped_column(Integer, default=0)
    attendance_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[AttendanceStatus] = mapped_column(Enum(AttendanceStatus), default=AttendanceStatus.absent)
    first_joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    session = relationship("CourseSession", back_populates="attendance_records")
