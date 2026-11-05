from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import select

from app.models import FaceEmbedding
from app.vision.embedder import DetectedFace
from app.vision.gallery import enroll_students, load_matcher


class FakeEmbedder:
    """Stands in for InsightFace: returns preset faces per photo file name."""

    def __init__(self, faces_by_photo: dict[str, list[DetectedFace]]):
        self.faces_by_photo = faces_by_photo

    def detect(self, image_path: Path) -> list[DetectedFace]:
        if image_path.name not in self.faces_by_photo:
            raise ValueError(f"unreadable: {image_path.name}")
        return self.faces_by_photo[image_path.name]


def face(seed: int, score: float = 0.9) -> DetectedFace:
    v = np.random.default_rng(seed).normal(size=512).astype(np.float32)
    return DetectedFace(bbox=(0, 0, 10, 10), score=score, embedding=v / np.linalg.norm(v))


def test_enrollment_reports_each_photo_outcome(session):
    embedder = FakeEmbedder(
        {
            "student_01.jpg": [face(1)],  # one face: enrolled
            "student_02.jpg": [face(2)],  # one face: enrolled
            "student_03.jpg": [],  # no face
            "student_04.jpg": [face(4), face(44)],  # two faces: refused
            # student_05.jpg is missing from the mapping: treated as unreadable
        }
    )

    results = {r.student_no: r for r in enroll_students(session, embedder)}

    assert results["UGS-26-001"].status == "enrolled"
    assert results["UGS-26-002"].status == "enrolled"
    assert results["UGS-26-003"].status == "no_face"
    assert results["UGS-26-004"].status == "multiple_faces"
    assert results["UGS-26-004"].faces_found == 2
    assert results["UGS-26-005"].status == "unreadable"
    # Only the two valid photos are stored.
    assert len(session.scalars(select(FaceEmbedding)).all()) == 2


def test_only_students_with_photos_are_processed(session):
    results = enroll_students(session, FakeEmbedder({}))
    # Only students 1-5 have photos in the demo seed.
    assert len(results) == 5


def test_enrolled_faces_can_be_matched_back(session):
    faces = {
        "student_01.jpg": [face(1)],
        "student_02.jpg": [face(2)],
        "student_03.jpg": [face(3)],
    }
    enroll_students(session, FakeEmbedder(faces))
    matcher = load_matcher(session)

    assert len(matcher) == 3
    assert matcher.match(face(2).embedding).student_no == "UGS-26-002"


def test_reenrollment_replaces_old_embeddings(session):
    enroll_students(session, FakeEmbedder({"student_01.jpg": [face(1)]}))
    enroll_students(session, FakeEmbedder({"student_01.jpg": [face(1)]}))
    assert len(session.scalars(select(FaceEmbedding)).all()) == 1
