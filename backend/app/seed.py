"""Seed demo data: a coordinator, instructors, students, courses, live sessions.

Run with:  python -m app.seed
Creates enough running courses to exercise the coordinator dashboard.
"""
import secrets
from datetime import datetime, timedelta, timezone

from app.core.security import hash_password
from app.database import Base, SessionLocal, engine
from app.models import (
    Course,
    CourseSession,
    Enrollment,
    SessionStatus,
    User,
    UserRole,
)

NUM_COURSES = 12
STUDENTS_PER_COURSE = 8


def run() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            print("Data already present — skipping seed.")
            return

        now = datetime.now(timezone.utc)

        coordinator = User(
            email="coordinator@livetrain.dev",
            full_name="Coordinator",
            hashed_password=hash_password("password"),
            role=UserRole.coordinator,
        )
        db.add(coordinator)

        students: list[User] = []
        for i in range(NUM_COURSES * STUDENTS_PER_COURSE):
            students.append(
                User(
                    email=f"student{i}@livetrain.dev",
                    full_name=f"Student {i}",
                    hashed_password=hash_password("password"),
                    role=UserRole.student,
                )
            )
        db.add_all(students)
        db.flush()

        for c in range(NUM_COURSES):
            instructor = User(
                email=f"instructor{c}@livetrain.dev",
                full_name=f"Instructor {c}",
                hashed_password=hash_password("password"),
                role=UserRole.instructor,
            )
            db.add(instructor)
            db.flush()

            course = Course(
                title=f"Course {c + 1}: Live Training Track",
                description="Auto-generated demo course.",
                instructor_id=instructor.id,
            )
            db.add(course)
            db.flush()

            cohort = students[c * STUDENTS_PER_COURSE : (c + 1) * STUDENTS_PER_COURSE]
            for s in cohort:
                db.add(Enrollment(course_id=course.id, student_id=s.id))

            # A session that is live right now.
            db.add(
                CourseSession(
                    course_id=course.id,
                    title=f"Session 1 — {course.title}",
                    room_id=secrets.token_urlsafe(9),
                    scheduled_start=now - timedelta(minutes=10),
                    scheduled_end=now + timedelta(minutes=50),
                    actual_start=now - timedelta(minutes=10),
                    status=SessionStatus.live,
                )
            )

        db.commit()
        print(
            f"Seeded {NUM_COURSES} courses, {len(students)} students, "
            f"{NUM_COURSES} live sessions.\n"
            "Login: coordinator@livetrain.dev / password"
        )
    finally:
        db.close()


if __name__ == "__main__":
    run()
