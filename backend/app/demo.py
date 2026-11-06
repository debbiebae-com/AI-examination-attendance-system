"""Isolated presentation attendance; never clears or relaxes rules for real exams."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import Exam

DEMO_CODE = "EXAMLENS-DEMO"


def demo_exam(session, *, create=False):
    exam = session.scalar(select(Exam).where(Exam.course_code == DEMO_CODE).order_by(Exam.id))
    if exam is None and create:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        exam = Exam(course_code=DEMO_CODE, course_title="Recognition demonstration", hall="Local demonstration", starts_at=now, ends_at=now + timedelta(days=1))
        session.add(exam)
        session.commit()
    return exam
