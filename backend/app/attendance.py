from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.eligibility import check_eligibility
from app.models import AttendanceRecord, Exam, Registration, Student, FaceEmbedding
from app.demo import DEMO_CODE


class AttendanceError(Exception):
    """Base class for attendance marking failures."""


class UnknownExam(AttendanceError):
    pass


class UnknownStudent(AttendanceError):
    pass


class NotEligible(AttendanceError):
    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def mark_attendance(
    session: Session,
    *,
    exam_id: int,
    student_no: str,
    confidence: float | None = None,
    source: str = "manual",
    demonstration: bool = False,
    now: datetime | None = None,
) -> tuple[AttendanceRecord, bool]:
    """Record a student's attendance for an exam.

    Returns (record, created). If the student was already marked present, the
    existing record is returned with created=False and nothing is written.
    Raises NotEligible if the student fails any eligibility rule.
    """
    exam = session.get(Exam, exam_id)
    if exam is None:
        raise UnknownExam(f"Exam {exam_id} not found")

    student = session.scalar(select(Student).where(Student.student_no == student_no))
    if student is None:
        raise UnknownStudent(f"Student {student_no} not found")

    if demonstration:
        if exam.course_code != DEMO_CODE:
            raise AttendanceError("Demonstration attendance requires the isolated demo record")
        if session.scalar(select(FaceEmbedding.id).where(FaceEmbedding.student_id == student.id).limit(1)) is None:
            raise NotEligible(["No enrolled face samples"])
        source = "demo"

    existing = _find_record(session, exam_id, student.id)
    if existing is not None:
        return existing, False

    registered = (
        session.scalar(
            select(Registration.id).where(
                Registration.exam_id == exam_id,
                Registration.student_id == student.id,
            )
        )
        is not None
    )
    result = check_eligibility(
        registered=registered,
        fees_cleared=student.fees_cleared,
        suspended=student.suspended,
    )
    if not demonstration and not result.eligible:
        raise NotEligible(result.reasons)

    record = AttendanceRecord(
        exam_id=exam_id,
        student_id=student.id,
        recorded_at=now or datetime.now(timezone.utc).replace(tzinfo=None),
        confidence=confidence,
        source=source,
    )
    session.add(record)
    try:
        session.commit()
    except IntegrityError:
        # Another request marked this student between our check and our insert.
        session.rollback()
        return _find_record(session, exam_id, student.id), False
    return record, True


def _find_record(session: Session, exam_id: int, student_id: int) -> AttendanceRecord | None:
    return session.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.exam_id == exam_id,
            AttendanceRecord.student_id == student_id,
        )
    )
