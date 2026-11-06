"""Enroll students' reference photos as face embeddings, and load them for matching."""

from dataclasses import dataclass

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.models import FaceEmbedding, Student
from app.vision.capture_flow import Sample
from app.vision.embedder import FaceEmbedder
from app.vision.matcher import DEFAULT_MARGIN, DEFAULT_THRESHOLD, FaceMatcher

CAPTURE_PREFIX = "capture:"


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
    # Keep embeddings from live capture (source "capture:..."); only photo-based ones are replaced.
    session.execute(delete(FaceEmbedding).where(FaceEmbedding.source_photo.not_like(CAPTURE_PREFIX + "%")))
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

        usable = [f for f in faces if f.embedding is not None]
        if not usable:
            results.append(EnrollResult(student.student_no, photo, "no_face"))
        elif len(usable) > 1:
            results.append(EnrollResult(student.student_no, photo, "multiple_faces", faces_found=len(usable)))
        else:
            face = usable[0]
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


def save_capture_samples(
    session: Session, student_id: int, samples: list[Sample], prefix: str = CAPTURE_PREFIX
) -> None:
    """Store capture embeddings for one student, replacing any earlier ones with the same prefix.

    Desktop capture uses the default ``capture:`` prefix; web enrollment uses ``web:`` so the
    two sources are tracked separately while both remain available to the matcher.
    """
    session.execute(
        delete(FaceEmbedding).where(
            FaceEmbedding.student_id == student_id,
            FaceEmbedding.source_photo.like(prefix + "%"),
        )
    )
    for sample in samples:
        session.add(
            FaceEmbedding(
                student_id=student_id,
                embedding=np.asarray(sample.embedding, dtype=np.float32).tobytes(),
                source_photo=f"{prefix}{sample.step}:{sample.index}",
                det_score=sample.det_score,
            )
        )
    session.commit()


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
