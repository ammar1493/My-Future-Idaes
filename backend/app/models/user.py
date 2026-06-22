"""User account model with role-based access."""
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    admin = "admin"            # full platform control
    coordinator = "coordinator"  # monitors all running courses, owns the dashboard
    instructor = "instructor"  # teaches one or more courses
    student = "student"        # attends courses


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.student)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    taught_courses = relationship("Course", back_populates="instructor")
    enrollments = relationship("Enrollment", back_populates="student", cascade="all, delete-orphan")
