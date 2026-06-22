"""Course and enrollment models."""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    instructor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    # Per-course attendance policy overrides (fall back to global defaults when null).
    present_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    partial_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    instructor = relationship("User", back_populates="taught_courses")
    enrollments = relationship("Enrollment", back_populates="course", cascade="all, delete-orphan")
    sessions = relationship("CourseSession", back_populates="course", cascade="all, delete-orphan")


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("course_id", "student_id", name="uq_course_student"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    course = relationship("Course", back_populates="enrollments")
    student = relationship("User", back_populates="enrollments")
