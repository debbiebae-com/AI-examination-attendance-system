"""Populate the database with a simulated student body and exam timetable.

Usage (from backend/):
    uv run python -m app.seed            # seed if empty
    uv run python -m app.seed --reset    # drop everything and reseed
"""

import argparse
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal, engine
from app.models import Base, Exam, Registration, Student

PHOTO_DIR = "data/demo_photos"
# Only the first five students have synthetic enrollment photos.
PHOTO_COUNT = 5

# (student_no, full_name, programme, level, fees_cleared, suspended)
STUDENTS = [
    ("UGS-26-001", "Ama Mensah-Boateng", "BSc Computer Science", 200, True, False),
    ("UGS-26-002", "Kwame Asante", "BSc Electrical Engineering", 300, True, False),
    ("UGS-26-003", "Chioma Okafor", "BSc Information Systems", 200, True, False),
    ("UGS-26-004", "Kenji Watanabe", "BSc Computer Science", 400, True, False),
    ("UGS-26-005", "Kofi Owusu-Ansah", "BSc Mathematics", 100, True, False),
    ("UGS-26-006", "Abena Osei", "BSc Statistics", 200, True, False),
    ("UGS-26-007", "Yaw Darko", "BSc Computer Science", 100, True, False),
    ("UGS-26-008", "Efua Appiah", "BSc Business Administration", 300, True, False),
    ("UGS-26-009", "Tunde Adeyemi", "BSc Electrical Engineering", 400, True, False),
    ("UGS-26-010", "Akosua Frimpong", "BSc Information Systems", 100, True, False),
    ("UGS-26-011", "Daniel Quaye", "BSc Mathematics", 300, True, False),
    ("UGS-26-012", "Grace Nyarko", "BSc Computer Science", 200, True, False),
    ("UGS-26-013", "Samuel Boadi", "BSc Statistics", 100, False, False),  # fees not cleared
    ("UGS-26-014", "Esi Addo", "BSc Business Administration", 200, True, False),
    ("UGS-26-015", "Ibrahim Mohammed", "BSc Computer Science", 300, True, True),  # suspended
    ("UGS-26-016", "Linda Kyei", "BSc Information Systems", 400, True, False),
    ("UGS-26-017", "Emmanuel Tetteh", "BSc Electrical Engineering", 100, True, False),
    ("UGS-26-018", "Fatima Abdul-Rahman", "BSc Mathematics", 200, True, False),
    ("UGS-26-019", "Joseph Baffour", "BSc Statistics", 300, True, False),
    ("UGS-26-020", "Priscilla Amoako", "BSc Business Administration", 100, True, False),
]

# Exams and the indices (into STUDENTS) of the students registered for each.
EXAMS = [
    {
        "course_code": "CS101",
        "course_title": "Introduction to Programming",
        "hall": "Hall A",
        "starts_at": datetime(2026, 11, 10, 9, 0),
        "ends_at": datetime(2026, 11, 10, 11, 0),
        "registered": range(0, 15),
    },
    {
        "course_code": "MTH201",
        "course_title": "Linear Algebra",
        "hall": "Hall B",
        "starts_at": datetime(2026, 11, 10, 13, 0),
        "ends_at": datetime(2026, 11, 10, 15, 0),
        "registered": range(9, 20),
    },
]


def populate(session: Session) -> bool:
    """Insert demo data. Returns False (and does nothing) if data already exists."""
    if session.scalar(select(Student.id).limit(1)) is not None:
        return False

    students: list[Student] = []
    for index, (student_no, name, programme, level, fees_cleared, suspended) in enumerate(STUDENTS):
        photo = f"{PHOTO_DIR}/student_{index + 1:02d}.jpg" if index < PHOTO_COUNT else None
        students.append(
            Student(
                student_no=student_no,
                full_name=name,
                programme=programme,
                level=level,
                fees_cleared=fees_cleared,
                suspended=suspended,
                photo_path=photo,
            )
        )
    session.add_all(students)
    session.flush()

    for spec in EXAMS:
        exam = Exam(
            course_code=spec["course_code"],
            course_title=spec["course_title"],
            hall=spec["hall"],
            starts_at=spec["starts_at"],
            ends_at=spec["ends_at"],
        )
        session.add(exam)
        session.flush()
        for index in spec["registered"]:
            session.add(Registration(student_id=students[index].id, exam_id=exam.id))

    session.commit()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="drop all tables before seeding")
    args = parser.parse_args()

    if args.reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    with SessionLocal() as session:
        seeded = populate(session)
    print("Seeded demo data." if seeded else "Database already has data; nothing changed (use --reset).")


if __name__ == "__main__":
    main()
