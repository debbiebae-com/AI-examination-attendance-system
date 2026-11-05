from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.attendance import NotEligible, UnknownExam, UnknownStudent, mark_attendance
from app.config import CORS_ORIGINS, ENROLL_DEFAULT_EXAM, ENROLL_MODEL, FRONTEND_DIR
from app.db import engine, get_session
from app.models import AttendanceRecord, Base, Exam, FaceEmbedding, Student
from app.vision.web_enroll import decode_image, enroll_from_photos


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Create tables on first boot so a fresh hosted database (e.g. Supabase) just works.
    Base.metadata.create_all(engine)
    yield


app = FastAPI(
    title="AI Examination Attendance API",
    version="0.1.0",
    description="REST API for exams, students, attendance records and web face enrollment.",
    lifespan=lifespan,
)

# Allow the phone web app (possibly hosted on a different origin) to call the API.
_origins = ["*"] if CORS_ORIGINS.strip() == "*" else [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# The face model is heavy; load it once, lazily, on the first enrollment request.
_embedder = None


def get_embedder():
    global _embedder
    if _embedder is None:
        from app.vision.embedder import InsightFaceEmbedder

        _embedder = InsightFaceEmbedder(liveness=False, model_name=ENROLL_MODEL)
    return _embedder


class AttendanceIn(BaseModel):
    student_no: str
    confidence: float | None = None
    source: str = "manual"


class EnrollPhoto(BaseModel):
    step: str = "straight"  # pose label: straight / left / right
    image: str  # base64 JPEG/PNG, optionally a data URL


class EnrollIn(BaseModel):
    full_name: str
    student_no: str
    photos: list[EnrollPhoto]
    exam: str | None = None


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
    sample_counts = dict(
        session.execute(
            select(FaceEmbedding.student_id, func.count(FaceEmbedding.id)).group_by(FaceEmbedding.student_id)
        ).all()
    )
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
            "face_samples": sample_counts.get(s.id, 0),
        }
        for s in students
    ]


@app.post("/enroll")
def enroll(body: EnrollIn, session: Session = Depends(get_session)) -> dict:
    """Enroll a student from phone-camera photos: compute face embeddings and store them."""
    if not body.photos:
        raise HTTPException(status_code=400, detail="At least one photo is required")

    photos = []
    for photo in body.photos:
        image = decode_image(photo.image)
        if image is None:
            raise HTTPException(status_code=400, detail=f"The '{photo.step}' photo could not be read")
        photos.append((photo.step, image))

    try:
        embedder = get_embedder()
    except Exception as exc:  # model not installed / failed to load
        raise HTTPException(status_code=503, detail=f"Face model is unavailable: {exc}") from exc

    result = enroll_from_photos(
        session,
        embedder,
        student_no=body.student_no,
        full_name=body.full_name,
        photos=photos,
        exam_code=body.exam or ENROLL_DEFAULT_EXAM,
    )
    if not result.ok:
        raise HTTPException(status_code=422, detail={"problems": result.problems})

    return {
        "ok": True,
        "student_no": result.student_no,
        "full_name": result.full_name,
        "samples_saved": result.samples_saved,
        "registered_exam": result.registered_exam,
        "warnings": result.problems,
    }


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


# Serve the compiled student app (frontend/dist) from the same server.
# API routes above take precedence; the static mount only catches /app paths.
if FRONTEND_DIR.exists():
    app.mount("/app", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="app")

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/app/")
