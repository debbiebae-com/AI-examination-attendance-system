"""Local cross-process attendance snapshot. No camera, vision models or network required.

SQLite makes publishing atomic for the separate CLI and API processes. Only the owning
session may publish; a lease permits recovery after a crashed process. No images or
embeddings are written here. Attendance remains in the normal application database.
"""
import json
import sqlite3
import time
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.config import DATA_DIR

LIVE_PATH = DATA_DIR / "live_session.db"
STALE_SECONDS = 120
MAX_EVENTS = 100


def stamp():
    return datetime.now(timezone.utc).isoformat()


class LiveStore:
    def __init__(self, path=LIVE_PATH):
        self.path = Path(path)

    @contextmanager
    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=2)
        db.execute("CREATE TABLE IF NOT EXISTS live (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
        try:
            with db:
                yield db
        finally:
            db.close()

    def publish(self, payload, *, claim=False):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM live WHERE id=1").fetchone()
            old = json.loads(row[0]) if row else None
            if old and old["session_id"] != payload["session_id"]:
                active = old["status"] in ("starting", "running")
                fresh = time.time() - old["heartbeat"] <= STALE_SECONDS
                if not claim or (active and fresh):
                    raise RuntimeError("Another attendance session owns the live feed")
            db.execute("INSERT OR REPLACE INTO live VALUES (1, ?)", (json.dumps(payload),))

    def reset_display(self, expected, *, exam_id=None, demo_mode=False):
        """Atomically clear a stopped snapshot, never a newly claimed camera session."""
        from fastapi import HTTPException
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM live WHERE id=1").fetchone()
            old = json.loads(row[0]) if row else {}
            version = [old.get(k) for k in ("session_id", "updated_at", "latest_event_id")]
            if version != expected or old.get("status") in ("starting", "running"):
                raise HTTPException(409, "Live session changed; stop recognition and preview again")
            payload = {
                **{k: old[k] for k in ("exam_id", "demo_mode", "demo_classroom", "classroom_name") if k in old},
                "session_id": str(uuid4()), "status": "idle", "updated_at": stamp(),
                "heartbeat": time.time(), "identified_count": 0, "unidentified_now": 0,
                "visible_faces": 0, "processed_fps": 0.0, "processing_ms": 0.0,
                "events": [], "latest_event_id": 0, "error": None,
            }
            if demo_mode:
                payload.update(exam_id=exam_id, demo_mode=True, demo_classroom=True, classroom_name="Recognition demonstration")
            db.execute("INSERT OR REPLACE INTO live VALUES (1, ?)", (json.dumps(payload),))

    def read(self, after=0):
        with self._connect() as db:
            row = db.execute("SELECT payload FROM live WHERE id=1").fetchone()
        if row is None:
            return {"session_id": None, "status": "idle", "events": [], "unidentified_now": 0}
        payload = json.loads(row[0])
        payload["stale"] = (payload["status"] in ("starting", "running") and
                            time.time() - payload["heartbeat"] > STALE_SECONDS)
        if payload["stale"]:
            payload["status"] = "disconnected"
        if payload["status"] != "running":
            payload["unidentified_now"] = 0
            payload["visible_faces"] = 0
        events = payload["events"]
        payload["events_truncated"] = bool(events and after and after < events[0]["id"] - 1)
        payload["events"] = [event for event in events if event["id"] > after]
        return payload


class LivePublisher:
    def __init__(self, exam_id, *, store=None):
        self.store = store or LiveStore()
        self.events = deque(maxlen=MAX_EVENTS)
        self.identified = set()
        self._last_states = {}
        self._unknown_since = {}
        self._last_publish = 0.0
        self.payload = {
            "session_id": str(uuid4()), "exam_id": exam_id,
            "started_at": stamp(), "updated_at": stamp(), "heartbeat": time.time(),
            "status": "starting", "error": None, "identified_count": 0,
            "unidentified_now": 0, "visible_faces": 0, "processed_fps": 0.0,
            "processing_ms": 0.0, "events": [], "latest_event_id": 0,
        }

    def __enter__(self):
        self.store.publish(self.payload, claim=True)
        return self

    def event(self, kind, *, track_id=None, student_no=None, **details):
        self.payload["latest_event_id"] += 1
        self.events.append({"id": self.payload["latest_event_id"], "at": stamp(),
                            "kind": kind, "track_id": track_id,
                            "student_no": student_no, **details})
        if kind == "identified" and student_no:
            self.identified.add(student_no)

    def observe(self, track_id, action, student_no=None):
        """Emit state transitions, not one event for every repeated frame."""
        state = (action, student_no)
        if self._last_states.get(track_id) != state:
            self._last_states[track_id] = state
            if action != "marked":
                self.event("identified" if action == "confirmed" else action,
                           track_id=track_id, student_no=student_no)

    def frame(self, *, visible_faces, states, fps, processing_ms, now=None):
        now = time.monotonic() if now is None else now
        visible = set(states)
        self._last_states = {k: v for k, v in self._last_states.items() if k in visible}
        for tid in list(self._unknown_since):
            if states.get(tid) != "unknown":
                del self._unknown_since[tid]
        for tid, state in states.items():
            if state == "unknown":
                self._unknown_since.setdefault(tid, now)
        self.payload.update(status="running", visible_faces=visible_faces,
                            unidentified_now=sum(now - t >= 0.5 for t in self._unknown_since.values()),
                            processed_fps=round(fps, 2), processing_ms=round(processing_ms, 2))
        if now - self._last_publish >= 0.5:
            self.flush()
            self._last_publish = now

    def flush(self):
        self.payload.update(updated_at=stamp(), heartbeat=time.time(),
                            identified_count=len(self.identified), events=list(self.events))
        self.store.publish(self.payload)

    def __exit__(self, exc_type, exc, tb):
        # Ctrl+C is a normal stop; camera/model/database failures are not.
        failed = exc is not None and not isinstance(exc, KeyboardInterrupt)
        self.payload.update(status="error" if failed else "stopped",
                            error=str(exc) if failed else None,
                            visible_faces=0, unidentified_now=0)
        self.event("error" if failed else "stopped")
        self.flush()
