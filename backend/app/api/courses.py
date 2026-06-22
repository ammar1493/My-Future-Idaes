"""Course CRUD and enrollment management."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_coordinator, require_staff
from app.database import get_db
from app.models import Course, Enrollment, User, UserRole
from app.schemas import CourseCreate, CourseOut, EnrollRequest, UserOut

router = APIRouter(prefix="/api/courses", tags=["courses"])


@router.get("", response_model=list[CourseOut])
def list_courses(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.execute(select(Course)).scalars().all()


@router.post("", response_model=CourseOut)
def create_course(
    payload: CourseCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    course = Course(**payload.model_dump())
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


@router.get("/{course_id}", response_model=CourseOut)
def get_course(course_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.post("/{course_id}/enroll", response_model=UserOut)
def enroll_student(
    course_id: int,
    payload: EnrollRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    student = db.get(User, payload.student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    existing = db.execute(
        select(Enrollment).where(
            Enrollment.course_id == course_id, Enrollment.student_id == payload.student_id
        )
    ).scalar_one_or_none()
    if not existing:
        db.add(Enrollment(course_id=course_id, student_id=payload.student_id))
        db.commit()
    return student


@router.get("/{course_id}/students", response_model=list[UserOut])
def list_students(course_id: int, db: Session = Depends(get_db), _: User = Depends(require_staff)):
    rows = db.execute(
        select(User).join(Enrollment, Enrollment.student_id == User.id).where(
            Enrollment.course_id == course_id
        )
    ).scalars().all()
    return rows
