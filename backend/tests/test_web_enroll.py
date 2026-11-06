import base64

import numpy as np
import pytest
from sqlalchemy import select

from app.models import Exam, FaceEmbedding, Registration, Student
from app.vision.embedder import DetectedFace
from app.vision.web_enroll import WEB_PREFIX, decode_image, enroll_from_photos


def emb(seed):
    v = np.random.default_rng(seed).normal(size=512).astype(np.float32)
    return v / np.linalg.norm(v)


def img_with_faces(n):
    """A tiny image whose first pixel encodes how many faces the fake embedder should report."""
    arr = np.zeros((20, 20, 3), dtype=np.uint8)
    arr[0, 0, 0] = n
    return arr


class FakeEmbedder:
    def analyse(self, image):
        n = int(image[0, 0, 0])
        return [DetectedFace(bbox=(0, 0, 10, 10), score=0.9, embedding=emb(k + 1)) for k in range(n)]


# ---- pure logic (no OpenCV needed) ---------------------------------------


def test_enroll_creates_student_and_saves_samples(session):
    photos = [("straight", img_with_faces(1)), ("left", img_with_faces(1)), ("right", img_with_faces(1))]
    result = enroll_from_photos(session, FakeEmbedder(), student_no="VOL-100", full_name="Ama Tester", photos=photos)

    assert result.ok
    assert result.samples_saved == 3
    student = session.scalar(select(Student).where(Student.student_no == "VOL-100"))
    assert student is not None and student.full_name == "Ama Tester"
    rows = session.scalars(select(FaceEmbedding).where(FaceEmbedding.student_id == student.id)).all()
    assert len(rows) == 3
    assert all(r.source_photo.startswith(WEB_PREFIX) for r in rows)


def test_enroll_requires_name_and_index(session):
    result = enroll_from_photos(session, FakeEmbedder(), student_no="  ", full_name="X", photos=[("straight", img_with_faces(1))])
    assert not result.ok
    assert any("required" in p for p in result.problems)


def test_enroll_rejects_when_no_face(session):
    result = enroll_from_photos(session, FakeEmbedder(), student_no="VOL-101", full_name="No Face", photos=[("straight", img_with_faces(0))])
    assert not result.ok
    assert any("no face" in p for p in result.problems)
    assert session.scalar(select(Student).where(Student.student_no == "VOL-101")) is None


def test_enroll_skips_multi_face_photo_but_keeps_good_ones(session):
    photos = [("straight", img_with_faces(1)), ("left", img_with_faces(2)), ("right", img_with_faces(1))]
    result = enroll_from_photos(session, FakeEmbedder(), student_no="VOL-102", full_name="Partial", photos=photos)
    assert result.ok
    assert result.samples_saved == 2
    assert any("more than one face" in p for p in result.problems)


def test_enroll_registers_for_exam(session):
    exam = session.scalar(select(Exam).where(Exam.course_code == "CS101"))
    photos = [("straight", img_with_faces(1))]
    result = enroll_from_photos(session, FakeEmbedder(), student_no="VOL-103", full_name="Reg", photos=photos, exam_code="CS101")
    assert result.ok and result.registered_exam == "CS101"
    student = session.scalar(select(Student).where(Student.student_no == "VOL-103"))
    reg = session.scalar(select(Registration.id).where(Registration.student_id == student.id, Registration.exam_id == exam.id))
    assert reg is not None


def test_reenroll_replaces_previous_web_samples(session):
    photos = [("straight", img_with_faces(1)), ("left", img_with_faces(1))]
    enroll_from_photos(session, FakeEmbedder(), student_no="VOL-104", full_name="Repeat", photos=photos)
    enroll_from_photos(session, FakeEmbedder(), student_no="VOL-104", full_name="Repeat", photos=photos)
    student = session.scalar(select(Student).where(Student.student_no == "VOL-104"))
    rows = session.scalars(select(FaceEmbedding).where(FaceEmbedding.student_id == student.id)).all()
    assert len(rows) == 2  # replaced, not duplicated


def test_enroll_updates_name_on_reenroll(session):
    enroll_from_photos(session, FakeEmbedder(), student_no="VOL-105", full_name="Old Name", photos=[("straight", img_with_faces(1))])
    enroll_from_photos(session, FakeEmbedder(), student_no="VOL-105", full_name="New Name", photos=[("straight", img_with_faces(1))])
    student = session.scalar(select(Student).where(Student.student_no == "VOL-105"))
    assert student.full_name == "New Name"


# ---- decode + endpoint (need OpenCV) -------------------------------------


def _jpeg_b64():
    cv2 = pytest.importorskip("cv2")
    img = np.full((30, 30, 3), 128, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return base64.b64encode(buf.tobytes()).decode()


def test_decode_image_roundtrip():
    pytest.importorskip("cv2")
    b64 = _jpeg_b64()
    assert decode_image(b64) is not None
    assert decode_image("data:image/jpeg;base64," + b64) is not None
    assert decode_image("not-valid-base64!!!") is None
    assert decode_image("") is None


def _client(session, monkeypatch, faces=1):
    pytest.importorskip("cv2")
    from fastapi.testclient import TestClient

    from app.db import get_session
    from app.main import app

    class Fake:
        def analyse(self, image):
            return [DetectedFace(bbox=(0, 0, 10, 10), score=0.9, embedding=emb(k + 1)) for k in range(faces)]

    monkeypatch.setattr("app.main.get_embedder", lambda: Fake())
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app), app


def test_enroll_endpoint_success(session, monkeypatch):
    client, app = _client(session, monkeypatch, faces=1)
    try:
        payload = {
            "full_name": "Endpoint User",
            "student_no": "VOL-200",
            "photos": [{"step": "straight", "image": _jpeg_b64()}],
        }
        res = client.post("/enroll", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] and data["samples_saved"] == 1 and data["student_no"] == "VOL-200"
    finally:
        app.dependency_overrides.clear()


def test_enroll_endpoint_no_face_returns_422(session, monkeypatch):
    client, app = _client(session, monkeypatch, faces=0)
    try:
        payload = {
            "full_name": "No Face",
            "student_no": "VOL-201",
            "photos": [{"step": "straight", "image": _jpeg_b64()}],
        }
        res = client.post("/enroll", json=payload)
        assert res.status_code == 422
        assert "problems" in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_enroll_endpoint_bad_image_returns_400(session, monkeypatch):
    client, app = _client(session, monkeypatch, faces=1)
    try:
        payload = {
            "full_name": "Bad Image",
            "student_no": "VOL-202",
            "photos": [{"step": "straight", "image": "@@@not-base64@@@"}],
        }
        res = client.post("/enroll", json=payload)
        assert res.status_code == 400
    finally:
        app.dependency_overrides.clear()
