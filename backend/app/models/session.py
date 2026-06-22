"""Live session (a single scheduled meeting of a course)."""
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SessionStatus(str, enum.Enum):
    scheduled = "scheduled"
    live = "live"
    ended = "ended"
    cancelled = "cancelled"


class CourseSession(Base):
    """One scheduled live class. The video room is keyed by `room_id`."""

    __tablename__ = "course_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    room_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[SessionStatus] = mapped_column(Enum(SessionStatus), default=SessionStatus.scheduled)

    course = relationship("Course", back_populates="sessions")
    presence_events = relationship("PresenceEvent", back_populates="session", cascade="all, delete-orphan")
    attendance_records = relationship("AttendanceRecord", back_populates="session", cascade="all, delete-orphan")
