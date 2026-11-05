import json
import urllib.request

import numpy as np
from sqlalchemy import select

from app.models import FaceEmbedding, Student
from app.sync import SupabaseInbox, sync_submissions
from app.vision.embedder import DetectedFace


def emb(seed):
    v = np.random.default_rng(seed).normal(size=512).astype(np.float32)
    return v / np.linalg.norm(v)


def img_with_faces(n):
    arr = np.zeros((20, 20, 3), dtype=np.uint8)
    arr[0, 0, 0] = n
    return arr


def fake_decode(data):
    # Test photos encode the face count as "faces:N"; anything else is "unreadable".
    if isinstance(data, str) and data.startswith("faces:"):
        return img_with_faces(int(data.split(":")[1]))
    return None


class FakeEmbedder:
    def analyse(self, image):
        n = int(image[0, 0, 0])
        return [DetectedFace(bbox=(0, 0, 10, 10), score=0.9, embedding=emb(k + 1)) for k in range(n)]


class FakeInbox:
    def __init__(self, subs):
        self.subs = subs
        self.synced = {}
        self.failed = {}

    def fetch_pending(self, limit=None):
        pend = [s for s in self.subs if s["status"] == "pending"]
        return pend[:limit] if limit else pend

    def mark_synced(self, sid, clear_photos=True):
        self.synced[sid] = clear_photos
        for s in self.subs:
            if s["id"] == sid:
                s["status"] = "synced"

    def mark_failed(self, sid, error):
        self.failed[sid] = error
        for s in self.subs:
            if s["id"] == sid:
                s["status"] = "failed"


def make_sub(sid, no, name, faces=1, exam=None):
    return {
        "id": sid,
        "student_no": no,
        "full_name": name,
        "exam": exam,
        "photos": [{"step": "straight", "image": f"faces:{faces}"}],
        "status": "pending",
    }


def test_sync_success_creates_student_and_clears_photos(session, monkeypatch):
    monkeypatch.setattr("app.sync.decode_image", fake_decode)
    inbox = FakeInbox([make_sub("a", "VOL-300", "Sync User")])
    report = sync_submissions(session, FakeEmbedder(), inbox)

    assert report.synced == ["Sync User (VOL-300)"]
    assert inbox.synced["a"] is True  # photos cleared by default
    student = session.scalar(select(Student).where(Student.student_no == "VOL-300"))
    assert student is not None
    rows = session.scalars(select(FaceEmbedding).where(FaceEmbedding.student_id == student.id)).all()
    assert len(rows) == 1


def test_sync_no_face_marks_failed(session, monkeypatch):
    monkeypatch.setattr("app.sync.decode_image", fake_decode)
    inbox = FakeInbox([make_sub("b", "VOL-301", "No Face", faces=0)])
    report = sync_submissions(session, FakeEmbedder(), inbox)

    assert report.synced == []
    assert len(report.failed) == 1
    assert "b" in inbox.failed
    assert session.scalar(select(Student).where(Student.student_no == "VOL-301")) is None


def test_sync_unreadable_photo_marks_failed(session, monkeypatch):
    monkeypatch.setattr("app.sync.decode_image", fake_decode)
    sub = make_sub("c", "VOL-302", "Bad Photo")
    sub["photos"] = [{"step": "straight", "image": "not-an-image"}]
    inbox = FakeInbox([sub])
    report = sync_submissions(session, FakeEmbedder(), inbox)

    assert len(report.failed) == 1
    assert "could not be read" in inbox.failed["c"]


def test_sync_keep_photos_flag(session, monkeypatch):
    monkeypatch.setattr("app.sync.decode_image", fake_decode)
    inbox = FakeInbox([make_sub("d", "VOL-303", "Keep Photos")])
    sync_submissions(session, FakeEmbedder(), inbox, keep_photos=True)
    assert inbox.synced["d"] is False  # not cleared


def test_sync_default_exam_fallback(session, monkeypatch):
    monkeypatch.setattr("app.sync.decode_image", fake_decode)
    inbox = FakeInbox([make_sub("e", "VOL-304", "Exam Fallback", exam=None)])
    report = sync_submissions(session, FakeEmbedder(), inbox, default_exam="CS101")
    assert report.synced == ["Exam Fallback (VOL-304)"]


def test_sync_is_idempotent_on_rerun(session, monkeypatch):
    monkeypatch.setattr("app.sync.decode_image", fake_decode)
    inbox = FakeInbox([make_sub("f", "VOL-305", "Repeat")])
    sync_submissions(session, FakeEmbedder(), inbox)
    report2 = sync_submissions(session, FakeEmbedder(), inbox)  # nothing pending now
    assert report2.total == 0
    student = session.scalar(select(Student).where(Student.student_no == "VOL-305"))
    rows = session.scalars(select(FaceEmbedding).where(FaceEmbedding.student_id == student.id)).all()
    assert len(rows) == 1  # not duplicated


# ---- Supabase REST contract -------------------------------------------------


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_supabase_inbox_request_contract(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["method"] = req.get_method()
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        captured["body"] = json.loads(req.data.decode()) if req.data else None
        return FakeResponse([{"id": "x", "status": "pending"}])

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    inbox = SupabaseInbox("https://proj.supabase.co", "secret-key")

    inbox.fetch_pending()
    assert captured["method"] == "GET"
    assert "/rest/v1/enroll_submissions?status=eq.pending" in captured["url"]
    assert captured["headers"].get("Apikey") == "secret-key"
    assert captured["headers"].get("Authorization") == "Bearer secret-key"

    inbox.mark_synced("x", clear_photos=True)
    assert captured["method"] == "PATCH"
    assert "id=eq.x" in captured["url"]
    assert captured["body"]["status"] == "synced"
    assert captured["body"]["photos"] is None
