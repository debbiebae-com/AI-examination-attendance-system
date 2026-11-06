"""Register students for an exam and check who is ready for camera attendance.

A student can only be marked present if they are (1) enrolled with face samples,
(2) registered for the exam, (3) fees cleared, and (4) not suspended. Capture with
``--exam`` registers automatically; this tool lets you register or check afterwards
without re-running the face capture.

Usage (from backend/):

    uv run python -m app.register --exam CS101 --student-no VOL-001 VOL-002 VOL-003
    uv run python -m app.register --exam CS101 --list
"""

import argparse

from sqlalchemy import func, select

from app.db import SessionLocal, engine
from app.eligibility import check_eligibility
from app.models import Base, Exam, FaceEmbedding, Registration, Student


def register_students(session, exam: Exam, student_nos: list[str]) -> None:
    for student_no in student_nos:
        student = session.scalar(select(Student).where(Student.student_no == student_no))
        if student is None:
            print(f"  {student_no}: no such student. Enroll them first (capture --student-no {student_no} --name ...)")
            continue
        already = session.scalar(
            select(Registration.id).where(
                Registration.student_id == student.id, Registration.exam_id == exam.id
            )
        )
        if already is not None:
            print(f"  {student_no}: already registered for {exam.course_code}")
            continue
        session.add(Registration(student_id=student.id, exam_id=exam.id))
        print(f"  {student_no}: registered for {exam.course_code}")
    session.commit()


def list_status(session, exam: Exam) -> None:
    sample_counts = dict(
        session.execute(
            select(FaceEmbedding.student_id, func.count(FaceEmbedding.id)).group_by(FaceEmbedding.student_id)
        ).all()
    )
    registered_ids = set(
        session.scalars(select(Registration.student_id).where(Registration.exam_id == exam.id)).all()
    )

    students = session.scalars(select(Student).order_by(Student.student_no)).all()
    # Show anyone registered for the exam or holding face samples (e.g. new volunteers).
    relevant = [s for s in students if s.id in registered_ids or sample_counts.get(s.id, 0) > 0]
    if not relevant:
        print("No enrolled or registered students yet. Run the face capture first.")
        return

    print(f"{'Student':<18}{'Name':<26}{'Registered':<12}{'Faces':<7}{'Eligible'}")
    print("-" * 82)
    for student in relevant:
        registered = student.id in registered_ids
        faces = sample_counts.get(student.id, 0)
        result = check_eligibility(
            registered=registered, fees_cleared=student.fees_cleared, suspended=student.suspended
        )
        eligible = "yes" if result.eligible else "no (" + "; ".join(result.reasons) + ")"
        print(
            f"{student.student_no:<18}{student.full_name:<26}{'yes' if registered else 'NO':<12}"
            f"{faces:<7}{eligible}"
        )
    print("\n'Registered=NO' or 'Faces=0' means attendance will not record that person.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--exam", required=True, help="course code, e.g. CS101")
    parser.add_argument("--student-no", nargs="*", default=[], help="student numbers to register for the exam")
    parser.add_argument("--list", action="store_true", help="show registration / enrollment / eligibility status")
    args = parser.parse_args()

    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        exam = session.scalar(select(Exam).where(Exam.course_code == args.exam))
        if exam is None:
            raise SystemExit(f"No exam with course code {args.exam}")
        if args.student_no:
            print(f"Registering for {args.exam} ({exam.course_title}):")
            register_students(session, exam, args.student_no)
        if args.list or not args.student_no:
            print(f"\nStatus for {args.exam} ({exam.course_title}):")
            list_status(session, exam)


if __name__ == "__main__":
    main()
