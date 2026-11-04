from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.attendance import NotEligible, UnknownExam, UnknownStudent, mark_attendance
from app.db import get_session
from app.models import AttendanceRecord, Exam, Student

app = FastAPI(
    title="AI Examination Attendance API",
    version="0.1.0",
    description="REST API for exams, students and attendance records.",
)


class AttendanceIn(BaseModel):
    student_no: str
    confidence: float | None = None
    source: str = "manual"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/exams")
def list_exams(session: Session = Depends(get_session)) -> list[dict]:
    exams = session.scalars(select(Exam).order_by(Exam.starts_at)).all()
    return [
        {
            "id": e.id,
            "course_code": e.course_code,
            "course_title": e.course_title,
            "hall": e.hall,
            "starts_at": e.starts_at.isoformat(),
            "ends_at": e.ends_at.isoformat(),
        }
        for e in exams
    ]


@app.get("/students")
def list_students(session: Session = Depends(get_session)) -> list[dict]:
    students = session.scalars(select(Student).order_by(Student.student_no)).all()
    return [
        {
            "student_no": s.student_no,
            "full_name": s.full_name,
            "programme": s.programme,
            "level": s.level,
            "fees_cleared": s.fees_cleared,
            "suspended": s.suspended,
            "has_photo": s.photo_path is not None,
        }
        for s in students
    ]


@app.get("/exams/{exam_id}/attendance")
def list_attendance(exam_id: int, session: Session = Depends(get_session)) -> list[dict]:
    if session.get(Exam, exam_id) is None:
        raise HTTPException(status_code=404, detail=f"Exam {exam_id} not found")
    records = session.scalars(
        select(AttendanceRecord)
        .where(AttendanceRecord.exam_id == exam_id)
        .order_by(AttendanceRecord.recorded_at)
    ).all()
    return [
        {
            "student_no": r.student.student_no,
            "full_name": r.student.full_name,
            "recorded_at": r.recorded_at.isoformat(),
            "confidence": r.confidence,
            "source": r.source,
        }
        for r in records
    ]


@app.post("/exams/{exam_id}/attendance")
def record_attendance(
    exam_id: int,
    body: AttendanceIn,
    session: Session = Depends(get_session),
) -> dict:
    try:
        record, created = mark_attendance(
            session,
            exam_id=exam_id,
            student_no=body.student_no,
            confidence=body.confidence,
            source=body.source,
        )
    except UnknownExam as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnknownStudent as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotEligible as exc:
        raise HTTPException(status_code=403, detail={"reasons": exc.reasons}) from exc

    return {
        "created": created,
        "student_no": body.student_no,
        "recorded_at": record.recorded_at.isoformat(),
    }
