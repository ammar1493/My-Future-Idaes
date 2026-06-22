"""Pydantic request/response schemas."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models import AttendanceStatus, SessionStatus, UserRole


# ---- Auth / Users -------------------------------------------------------
class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: UserRole = UserRole.student


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---- Courses ------------------------------------------------------------
class CourseCreate(BaseModel):
    title: str
    description: str = ""
    instructor_id: int | None = None
    present_threshold: float | None = None
    partial_threshold: float | None = None


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: str
    instructor_id: int | None
    present_threshold: float | None
    partial_threshold: float | None


class EnrollRequest(BaseModel):
    student_id: int


# ---- Sessions -----------------------------------------------------------
class SessionCreate(BaseModel):
    course_id: int
    title: str = ""
    scheduled_start: datetime
    scheduled_end: datetime


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    course_id: int
    title: str
    room_id: str
    scheduled_start: datetime
    scheduled_end: datetime
    actual_start: datetime | None
    actual_end: datetime | None
    status: SessionStatus


# ---- Attendance ---------------------------------------------------------
class AttendanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    session_id: int
    user_id: int
    seconds_present: int
    attendance_ratio: float
    status: AttendanceStatus
    first_joined_at: datetime | None
    last_left_at: datetime | None


# ---- Dashboard ----------------------------------------------------------
class LiveCourseTile(BaseModel):
    session_id: int
    course_id: int
    course_title: str
    session_title: str
    room_id: str
    status: SessionStatus
    enrolled: int
    live_now: int
    scheduled_start: datetime
    scheduled_end: datetime


class DashboardSummary(BaseModel):
    total_live_sessions: int
    total_participants_live: int
    total_courses: int
    tiles: list[LiveCourseTile]
