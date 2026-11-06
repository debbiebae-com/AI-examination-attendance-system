from datetime import datetime

import pytest
from sqlalchemy import func, select

from app.attendance import NotEligible, mark_attendance
from app.models import AttendanceRecord, Exam
from app.seed import STUDENTS


def exam_id(session, course_code: str) -> int:
    return session.scalar(select(Exam.id).where(Exam.course_code == course_code))


def student_no(index: int) -> str:
    return STUDENTS[index][0]


def test_registered_eligible_student_is_marked(session):
    eid = exam_id(session, "CS101")
    record, created = mark_attendance(session, exam_id=eid, student_no=student_no(0), confidence=0.91, source="camera")
    assert created
    assert record.source == "camera"
    assert record.confidence == pytest.approx(0.91)


def test_duplicate_scan_does_not_create_second_record(session):
    eid = exam_id(session, "CS101")
    first, created_first = mark_attendance(session, exam_id=eid, student_no=student_no(0))
    second, created_second = mark_attendance(session, exam_id=eid, student_no=student_no(0))

    assert created_first is True
    assert created_second is False
    assert second.id == first.id
    count = session.scalar(select(func.count()).select_from(AttendanceRecord))
    assert count == 1


def test_same_student_can_attend_a_different_exam(session):
    # Student index 10 is registered for both exams in the demo timetable.
    cs = exam_id(session, "CS101")
    mth = exam_id(session, "MTH201")
    _, created_cs = mark_attendance(session, exam_id=cs, student_no=student_no(10))
    _, created_mth = mark_attendance(session, exam_id=mth, student_no=student_no(10))
    assert created_cs and created_mth


def test_unregistered_student_is_refused(session):
    eid = exam_id(session, "CS101")
    # Index 15 is only registered for MTH201.
    with pytest.raises(NotEligible) as info:
        mark_attendance(session, exam_id=eid, student_no=student_no(15))
    assert "Not registered for this exam" in info.value.reasons


def test_fees_not_cleared_is_refused(session):
    eid = exam_id(session, "CS101")
    # Index 12 is registered but has not cleared fees.
    with pytest.raises(NotEligible) as info:
        mark_attendance(session, exam_id=eid, student_no=student_no(12))
    assert info.value.reasons == ["Fees not cleared"]


def test_suspended_student_is_refused(session):
    eid = exam_id(session, "CS101")
    # Index 14 is registered but suspended.
    with pytest.raises(NotEligible) as info:
        mark_attendance(session, exam_id=eid, student_no=student_no(14))
    assert info.value.reasons == ["Suspended or on academic hold"]


def test_attendance_time_is_stored_as_given(session):
    eid = exam_id(session, "CS101")
    when = datetime(2026, 11, 10, 9, 5)
    record, _ = mark_attendance(session, exam_id=eid, student_no=student_no(1), now=when)
    assert record.recorded_at == when
