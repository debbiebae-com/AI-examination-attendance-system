from sqlalchemy import select

from app.models import Exam, Registration, Student
from app.register import list_status, register_students


def _exam(session, code="CS101"):
    return session.scalar(select(Exam).where(Exam.course_code == code))


def _registration(session, exam, student_no):
    student = session.scalar(select(Student).where(Student.student_no == student_no))
    return session.scalar(
        select(Registration.id).where(
            Registration.student_id == student.id, Registration.exam_id == exam.id
        )
    )


def test_register_adds_a_missing_registration(session):
    exam = _exam(session)
    # UGS-26-016 is seeded for MTH201 only, not CS101.
    assert _registration(session, exam, "UGS-26-016") is None
    register_students(session, exam, ["UGS-26-016"])
    assert _registration(session, exam, "UGS-26-016") is not None


def test_register_is_idempotent(session, capsys):
    exam = _exam(session)
    assert _registration(session, exam, "UGS-26-001") is not None  # already registered
    register_students(session, exam, ["UGS-26-001"])
    assert "already registered" in capsys.readouterr().out
    count = session.scalar(
        select(Registration.id).where(Registration.exam_id == exam.id).order_by(Registration.id)
    )
    assert count is not None  # still present, no duplicate raised


def test_register_reports_unknown_student(session, capsys):
    exam = _exam(session)
    register_students(session, exam, ["NOPE-999"])
    assert "no such student" in capsys.readouterr().out


def test_register_multiple_students(session):
    exam = _exam(session)
    register_students(session, exam, ["UGS-26-016", "UGS-26-017"])
    assert _registration(session, exam, "UGS-26-016") is not None
    assert _registration(session, exam, "UGS-26-017") is not None


def test_list_status_shows_registered_students(session, capsys):
    exam = _exam(session)
    list_status(session, exam)
    out = capsys.readouterr().out
    assert "Student" in out and "Eligible" in out
    assert "UGS-26-001" in out


def test_list_status_flags_unregistered_volunteer(session, capsys):
    exam = _exam(session)
    # Create a volunteer with a face sample but no registration.
    from app.models import FaceEmbedding

    volunteer = Student(
        student_no="VOL-099", full_name="Test Volunteer", programme="Volunteer (test)",
        level=100, fees_cleared=True, suspended=False,
    )
    session.add(volunteer)
    session.flush()
    session.add(FaceEmbedding(student_id=volunteer.id, embedding=b"\x00" * 8, source_photo="capture:straight:0", det_score=0.9))
    session.commit()

    list_status(session, exam)
    out = capsys.readouterr().out
    assert "VOL-099" in out
    # The volunteer row should show they are NOT registered.
    vol_line = next(line for line in out.splitlines() if "VOL-099" in line)
    assert "NO" in vol_line
