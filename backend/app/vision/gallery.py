"""Enroll students' reference photos as face embeddings, and load them for matching."""

from dataclasses import dataclass

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.models import FaceEmbedding, Student
from app.vision.embedder import FaceEmbedder
from app.vision.matcher import DEFAULT_MARGIN, DEFAULT_THRESHOLD, FaceMatcher


@dataclass(frozen=True)
class EnrollResult:
    student_no: str
    photo: str
    status: str  # "enrolled", "no_face", "multiple_faces", "missing_photo", "unreadable"
    faces_found: int = 0
    det_score: float | None = None


def enroll_students(session: Session, embedder: FaceEmbedder) -> list[EnrollResult]:
    """Replace all stored embeddings with fresh ones computed from enrollment photos.

    A photo is only enrolled if it contains exactly one face. Anything else is
    reported, so the operator can fix the photo.
    """
    session.execute(delete(FaceEmbedding))
    results: list[EnrollResult] = []

    students = session.scalars(
        select(Student).where(Student.photo_path.is_not(None)).order_by(Student.student_no)
    ).all()

    for student in students:
        photo = student.photo_path
        path = BASE_DIR / photo
        if not path.exists():
            results.append(EnrollResult(student.student_no, photo, "missing_photo"))
            continue
        try:
            faces = embedder.detect(path)
        except ValueError:
            results.append(EnrollResult(student.student_no, photo, "unreadable"))
            continue

        if not faces:
            results.append(EnrollResult(student.student_no, photo, "no_face"))
        elif len(faces) > 1:
            results.append(EnrollResult(student.student_no, photo, "multiple_faces", faces_found=len(faces)))
        else:
            face = faces[0]
            session.add(
                FaceEmbedding(
                    student_id=student.id,
                    embedding=np.asarray(face.embedding, dtype=np.float32).tobytes(),
                    source_photo=photo,
                    det_score=face.score,
                )
            )
            results.append(EnrollResult(student.student_no, photo, "enrolled", 1, face.score))

    session.commit()
    return results


def load_matcher(
    session: Session,
    threshold: float = DEFAULT_THRESHOLD,
    margin: float = DEFAULT_MARGIN,
) -> FaceMatcher:
    matcher = FaceMatcher(threshold=threshold, margin=margin)
    rows = session.execute(
        select(Student.student_no, FaceEmbedding.embedding).join(
            FaceEmbedding, FaceEmbedding.student_id == Student.id
        )
    ).all()
    for student_no, blob in rows:
        matcher.enroll(student_no, np.frombuffer(blob, dtype=np.float32))
    return matcher
