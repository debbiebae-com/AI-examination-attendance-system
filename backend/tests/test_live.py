import time

import pytest
from fastapi.testclient import TestClient

from app.live import LivePublisher, LiveStore, MAX_EVENTS, STALE_SECONDS
from app.main import app
from app.db import get_session


def test_separate_store_instances_share_atomic_snapshot(tmp_path):
    path = tmp_path / "live.db"
    with LivePublisher(1, store=LiveStore(path)) as live:
        live.observe(7, "confirmed", "VOL-1")
        live.frame(visible_faces=2, states={7: "confirmed", 8: "unknown"}, fps=8, processing_ms=120, now=1)
        live.frame(visible_faces=2, states={7: "marked", 8: "unknown"}, fps=8, processing_ms=120, now=2)
        snapshot = LiveStore(path).read()
        assert snapshot["status"] == "running"
        assert snapshot["identified_count"] == 1
        assert snapshot["unidentified_now"] == 1
        assert snapshot["processed_fps"] == 8
    assert LiveStore(path).read()["status"] == "stopped"
    assert LiveStore(path).read()["unidentified_now"] == 0


def test_events_are_bounded_debounced_and_cursor_filtered(tmp_path):
    store = LiveStore(tmp_path / "live.db")
    with LivePublisher(1, store=store) as live:
        for _ in range(20):
            live.observe(1, "unknown")
        assert len(live.events) == 1
        for _ in range(MAX_EVENTS + 5):
            live.event("checking")
        live.flush()
        snapshot = store.read(after=1)
        assert len(snapshot["events"]) == MAX_EVENTS
        assert snapshot["events_truncated"]
        assert store.read(after=snapshot["latest_event_id"])["events"] == []


def test_distinct_identity_count_and_unknown_grace(tmp_path):
    store = LiveStore(tmp_path / "live.db")
    with LivePublisher(1, store=store) as live:
        live.observe(1, "confirmed", "A")
        live.observe(2, "confirmed", "A")
        live.frame(visible_faces=1, states={3: "unknown"}, fps=1, processing_ms=1, now=1)
        assert store.read()["unidentified_now"] == 0
        live.frame(visible_faces=1, states={3: "unknown"}, fps=1, processing_ms=1, now=2)
        assert store.read()["unidentified_now"] == 1
        assert store.read()["identified_count"] == 1
        live.frame(visible_faces=0, states={}, fps=1, processing_ms=1, now=3)
        assert store.read()["unidentified_now"] == 0


def test_ownership_and_recovery(tmp_path):
    store = LiveStore(tmp_path / "live.db")
    first = LivePublisher(1, store=store)
    first.__enter__()
    second = LivePublisher(2, store=store)
    with pytest.raises(RuntimeError, match="Another attendance"):
        second.__enter__()
    first.payload["heartbeat"] = time.time() - STALE_SECONDS - 1
    store.publish(first.payload)
    assert store.read()["status"] == "disconnected"
    second.__enter__()
    with pytest.raises(RuntimeError):
        first.flush()
    second.__exit__(None, None, None)


def test_worker_error_and_interrupt_states(tmp_path):
    store = LiveStore(tmp_path / "live.db")
    with pytest.raises(RuntimeError, match="camera failed"):
        with LivePublisher(1, store=store):
            raise RuntimeError("camera failed")
    assert store.read()["status"] == "error"
    assert store.read()["error"] == "camera failed"
    with pytest.raises(KeyboardInterrupt):
        with LivePublisher(1, store=store):
            raise KeyboardInterrupt()
    assert store.read()["status"] == "stopped"


def test_live_api_idle_exam_and_present_scope(tmp_path, session, monkeypatch):
    from app import main
    from app.attendance import mark_attendance
    from app.models import Exam
    from sqlalchemy import select

    store = LiveStore(tmp_path / "live.db")
    monkeypatch.setattr(main, "LiveStore", lambda: store)
    app.dependency_overrides[get_session] = lambda: session
    try:
        client = TestClient(app)
        assert client.get("/live/session").json()["status"] == "idle"
        assert client.get("/live/session?after=-1").status_code == 422
        exam = session.scalar(select(Exam).where(Exam.course_code == "CS101"))
        mark_attendance(session, exam_id=exam.id, student_no="UGS-26-001")
        with LivePublisher(exam.id, store=store) as live:
            live.observe(1, "confirmed", "UGS-26-002")
            live.flush()
            data = client.get("/live/session").json()
            assert data["exam"]["course_code"] == "CS101"
            assert data["present_count"] == 1
            assert data["present_count_scope"] == "selected_exam_all_runs"
            assert data["identified_count"] == 1
    finally:
        app.dependency_overrides.clear()


def test_publication_is_readable_from_another_process(tmp_path):
    import json
    import subprocess
    import sys
    store = LiveStore(tmp_path / "cross-process.db")
    with LivePublisher(42, store=store) as live:
        live.observe(9, "confirmed", "VOL-42")
        live.flush()
        output = subprocess.check_output([
            sys.executable, "-c",
            "import json,sys; from app.live import LiveStore; print(json.dumps(LiveStore(sys.argv[1]).read()))",
            str(store.path),
        ], text=True)
        data = json.loads(output)
        assert data["session_id"] == live.payload["session_id"]
        assert data["identified_count"] == 1
        assert data["exam_id"] == 42
