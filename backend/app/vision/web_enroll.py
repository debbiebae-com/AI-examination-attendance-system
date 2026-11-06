"""Web enrollment: turn phone guided-capture frames into stored face embeddings.

The phone runs a live guided capture (look straight, turn left, turn right) that collects
several frames per pose automatically and posts them here. Each frame must contain exactly
one face; its ArcFace embedding is computed with the SAME model used by live attendance,
so the samples are directly usable for recognition.

This module is pure logic (no camera, no web framework) so it is unit tested with a fake
embedder. ``decode_image`` and the FastAPI endpoint live in main.py / drive this.
"""

import base64
from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Exam, Registration, Student
from app.vision.capture_flow import Sample
from app.vision.embedder import FaceEmbedder
from app.vision.gallery import save_capture_samples

WEB_PREFIX = "web:"
# The poses the web app asks for, in order. A photo is labelled with the pose it was taken at.
WEB_STEPS = ("straight", "left", "right")
MIN_SAMPLES = 1  # at least one usable face is required; three poses give the best matching


@dataclass
class WebEnrollResult:
    ok: bool
    student_no: str
    full_name: str
    samples_saved: int = 0
    registered_exam: str | None = None
    problems: list[str] = field(default_factory=list)


def decode_image(data: str) -> np.ndarray | None:
    """Decode a base64 image (optionally a data URL) into a BGR array. None if unreadable."""
    import cv2

    payload = data.strip()
    if payload.startswith("data:") and "," in payload:
        payload = payload.split(",", 1)[1]
    try:
        raw = base64.b64decode(payload, validate=True)
    except (ValueError, base64.binascii.Error):
        return None
    if not raw:
        return None
    image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    return image


def _get_or_create_student(session: Session, student_no: str, full_name: str) -> Student:
    student = session.scalar(select(Student).where(Student.student_no == student_no))
    if student is None:
        student = Student(
            student_no=student_no,
            full_name=full_name,
            programme="Volunteer (web)",
            level=100,
            fees_cleared=True,
            suspended=False,
        )
        session.add(student)
        session.flush()
    elif full_name and student.full_name != full_name:
        # Keep the name they typed on the form up to date.
        student.full_name = full_name
    return student


def _register_for_exam(session: Session, student: Student, exam_code: str) -> str | None:
    exam = session.scalar(select(Exam).where(Exam.course_code == exam_code))
    if exam is None:
        return None
    already = session.scalar(
        select(Registration.id).where(
            Registration.student_id == student.id, Registration.exam_id == exam.id
        )
    )
    if already is None:
        session.add(Registration(student_id=student.id, exam_id=exam.id))
    return exam.course_code


def enroll_from_photos(
    session: Session,
    embedder: FaceEmbedder,
    *,
    student_no: str,
    full_name: str,
    photos: list[tuple[str, np.ndarray]],
    exam_code: str | None = None,
) -> WebEnrollResult:
    """Create/update a student and store face embeddings from their uploaded photos.

    ``photos`` is a list of (pose_label, BGR image). Each photo must contain exactly one
    face. At least MIN_SAMPLES usable faces are required to save. If ``exam_code`` matches
    an exam, the student is also registered for it.
    """
    student_no = student_no.strip()
    full_name = full_name.strip()
    if not student_no or not full_name:
        return WebEnrollResult(False, student_no, full_name, problems=["Name and index number are required"])
    if not photos:
        return WebEnrollResult(False, student_no, full_name, problems=["No photos were submitted"])

    samples: list[Sample] = []
    problems: list[str] = []
    for label, image in photos:
        if image is None:
            problems.append(f"{label}: photo could not be read")
            continue
        faces = embedder.analyse(image)
        usable = [face for face in faces if face.embedding is not None]
        if len(usable) == 0:
            problems.append(f"{label}: no face found, retake this photo")
        elif len(usable) > 1:
            problems.append(f"{label}: more than one face in view, retake alone")
        else:
            face = usable[0]
            samples.append(Sample(label, len(samples), np.asarray(face.embedding, dtype=np.float32), face.score))

    if len(samples) < MIN_SAMPLES:
        return WebEnrollResult(False, student_no, full_name, problems=problems or ["No usable face photos"])

    student = _get_or_create_student(session, student_no, full_name)
    save_capture_samples(session, student.id, samples, prefix=WEB_PREFIX)

    registered = _register_for_exam(session, student, exam_code) if exam_code else None
    session.commit()

    return WebEnrollResult(
        ok=True,
        student_no=student.student_no,
        full_name=student.full_name,
        samples_saved=len(samples),
        registered_exam=registered,
        problems=problems,  # non-fatal warnings about photos that were skipped
    )
