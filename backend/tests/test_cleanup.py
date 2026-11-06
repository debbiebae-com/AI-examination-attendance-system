import pytest
from sqlalchemy import select

from app.cleanup import execute_cleanup, plan_cleanup, plan_inbox_purge
from app.models import AttendanceRecord, Exam, FaceEmbedding, Registration, Student


def _add_person(session, student_no, name, *, with_data=True):
    student = Student(
        student_no=student_no,
        full_name=name,
        programme="Volunteer (test)",
        level=100,
        fees_cleared=True,
        suspended=False,
    )
    session.add(student)
    session.flush()
    if with_data:
        exam = session.scalar(select(Exam).where(Exam.course_code == "CS101"))
        session.add(FaceEmbedding(student_id=student.id, embedding=b"\x00" * 8, source_photo="web:straight:0", det_score=0.9))
        session.add(Registration(student_id=student.id, exam_id=exam.id))
        session.add(AttendanceRecord(exam_id=exam.id, student_id=student.id, recorded_at=exam.starts_at, source="camera"))
    session.commit()
    return student


def test_cleanup_keeps_only_requested_person_and_dependents(session):
    keep = _add_person(session, "VOL-002", "Volunteer Two")
    _add_person(session, "VOL-001", "Volunteer One")
    _add_person(session, "PS/CSC/24/0016", "Rolandho David")

    plan = plan_cleanup(session, ["VOL-002"])
    assert [s.student_no for s in plan.kept] == ["VOL-002"]
    assert len(plan.removed) == 22  # 20 seeded demo students + VOL-001 + long-index volunteer

    counts = execute_cleanup(session, plan)
    assert counts.students == 22
    assert counts.embeddings >= 2
    assert counts.registrations >= 2
    assert counts.attendance >= 2

    remaining = session.scalars(select(Student)).all()
    assert [s.student_no for s in remaining] == ["VOL-002"]
    assert session.scalar(select(FaceEmbedding.student_id)) == keep.id
    assert session.scalar(select(Registration.student_id)) == keep.id
    assert session.scalar(select(AttendanceRecord.student_id)) == keep.id
    assert session.scalar(select(Exam.id)) is not None  # exams preserved


def test_cleanup_matches_name_case_insensitively(session):
    _add_person(session, "VOL-002", "Volunteer Two")
    plan = plan_cleanup(session, ["volunteer two"])
    assert [s.student_no for s in plan.kept] == ["VOL-002"]


def test_cleanup_keeps_long_index_number(session):
    _add_person(session, "PS/CSC/24/0016", "Rolandho David")
    plan = plan_cleanup(session, ["ps/csc/24/0016"])
    assert [s.student_no for s in plan.kept] == ["PS/CSC/24/0016"]
    execute_cleanup(session, plan)
    assert session.scalar(select(Student.student_no)) == "PS/CSC/24/0016"


def test_cleanup_unknown_identifier_is_an_error(session):
    with pytest.raises(ValueError, match="No person matches"):
        plan_cleanup(session, ["NOPE-999"])


def test_cleanup_requires_a_keep_identifier(session):
    with pytest.raises(ValueError, match="at least one"):
        plan_cleanup(session, [])


def test_plan_inbox_purge_keeps_only_requested_indices():
    class FakeInbox:
        def fetch_all_ids(self):
            return [
                {"id": "a", "student_no": "VOL-002"},
                {"id": "b", "student_no": "vol-001"},
                {"id": "c", "student_no": "PS/CSC/24/0016"},
            ]

    assert plan_inbox_purge(FakeInbox(), ["VOL-002"]) == ["b", "c"]
    assert plan_inbox_purge(FakeInbox(), ["vol-002", "ps/csc/24/0016"]) == ["b"]


def test_cleanup_nothing_to_remove(session):
    plan = plan_cleanup(session, ["UGS-26-001", "UGS-26-002", "UGS-26-003", "UGS-26-004", "UGS-26-005",
                                  "UGS-26-006", "UGS-26-007", "UGS-26-008", "UGS-26-009", "UGS-26-010",
                                  "UGS-26-011", "UGS-26-012", "UGS-26-013", "UGS-26-014", "UGS-26-015",
                                  "UGS-26-016", "UGS-26-017", "UGS-26-018", "UGS-26-019", "UGS-26-020"])
    assert plan.removed == []
    counts = execute_cleanup(session, plan)
    assert counts.students == 0
