import pytest
from sqlalchemy import select, func

from app.attendance import mark_attendance, AttendanceError, NotEligible
from app.demo import demo_exam
from app.models import FaceEmbedding, Student, Registration


def test_explicit_demo_mode_ignores_exam_eligibility_but_does_not_modify_it(session):
    exam = demo_exam(session, create=True)
    student = session.scalar(select(Student).where(Student.student_no == "UGS-26-020"))
    student.fees_cleared = False
    student.suspended = True
    session.add(FaceEmbedding(student_id=student.id, embedding=b"test", source_photo="capture:straight", det_score=1))
    session.commit()
    record, created = mark_attendance(session, exam_id=exam.id, student_no=student.student_no, demonstration=True)
    assert created and record.source == "demo"
    assert not student.fees_cleared and student.suspended
    assert session.scalar(select(func.count(Registration.id)).where(Registration.exam_id == exam.id)) == 0
    with pytest.raises(AttendanceError):
        mark_attendance(session, exam_id=1, student_no=student.student_no, demonstration=True)
    with pytest.raises(NotEligible):
        mark_attendance(session, exam_id=1, student_no=student.student_no)


def test_demo_attendance_still_requires_enrolled_faces(session):
    exam = demo_exam(session, create=True)
    with pytest.raises(NotEligible, match="No enrolled face samples"):
        mark_attendance(session, exam_id=exam.id, student_no="UGS-26-001", demonstration=True)
