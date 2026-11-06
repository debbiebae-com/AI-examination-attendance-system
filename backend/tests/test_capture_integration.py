"""End-to-end capture data flow without a camera or GUI.

Simulates a person moving through the prompts, feeding synthetic detections through the
real person-space mapping, capture sequence, threaded embed worker, reconciliation and
liveness gate, then saves to the seeded database. This exercises the same wiring main()
uses, minus OpenCV's window.
"""

import numpy as np
import pytest
from sqlalchemy import select

pytest.importorskip("cv2")

from app.models import FaceEmbedding, Student  # noqa: E402
from app.vision.capture import to_signal  # noqa: E402
from app.vision.capture_flow import CaptureSequence, liveness_summary, missing_steps  # noqa: E402
from app.vision.embedder import EmbedResult, GuidedFace  # noqa: E402
from app.vision.gallery import save_capture_samples  # noqa: E402
from app.vision.sample_worker import EmbedJob, SampleEmbedder, collect_samples  # noqa: E402

SHAPE = (480, 640, 3)


def emb(seed):
    v = np.random.default_rng(seed).normal(size=512).astype(np.float32)
    return v / np.linalg.norm(v)


def fake_embed(live=True):
    counter = {"n": 0}

    def embed_fn(image, bbox, kps):
        counter["n"] += 1
        return EmbedResult(embedding=emb(counter["n"]), is_live=live, live_score=0.9 if live else 0.1)

    return embed_fn


def scripted_guide(poses):
    """Yield GuidedFace lists for a scripted sequence of image-space yaws (mirrored feed)."""
    for yaw_image, eye in poses:
        yield [GuidedFace(bbox=(160, 120, 480, 360), score=0.9, pose=(0.0, yaw_image, 0.0), eye_ratio=eye)]


def run_capture(poses, *, live=True, mirrored=True, gap_frames=0):
    sequence = CaptureSequence(gap_frames=gap_frames)
    worker = SampleEmbedder(fake_embed(live=live)).start()
    frame = np.zeros(SHAPE, dtype=np.uint8)
    for faces in scripted_guide(poses):
        if sequence.done:
            break
        signal = to_signal(faces, SHAPE, mirrored=mirrored)
        verdict = sequence.process(signal)
        if verdict.accepted is not None:
            face = faces[0]
            accepted = sequence.accepted_frames[-1]
            worker.submit(EmbedJob(accepted.step, accepted.index, frame.copy(), face.bbox, face.kps, face.score))
    results = worker.finish()
    samples, problems = collect_samples(sequence.accepted_frames, results)
    live_ok, live_message = liveness_summary([r.is_live for r in results if r.embedding is not None])
    return sequence, samples, problems, live_ok, live_message


def straight_left_right():
    # Mirrored feed: person's left = negative image yaw. Hold each pose long enough for
    # the smoothed angle to settle and the required samples to be kept.
    yield from [(0.0, 0.3)] * 8  # straight
    yield from [(-30.0, 0.3)] * 12  # turn to own left
    yield from [(30.0, 0.3)] * 12  # turn to own right


def test_full_capture_produces_savable_samples(session):
    sequence, samples, problems, live_ok, _ = run_capture(list(straight_left_right()))
    assert sequence.done
    assert not problems
    assert live_ok
    assert missing_steps(samples) == []
    assert len(samples) == 9  # 3 + 3 + 3

    student = session.scalar(select(Student).where(Student.student_no == "UGS-26-001"))
    save_capture_samples(session, student.id, samples)
    rows = session.scalars(select(FaceEmbedding).where(FaceEmbedding.student_id == student.id)).all()
    assert len(rows) == 9
    assert all(row.source_photo.startswith("capture:") for row in rows)


def test_capture_with_dead_liveness_is_refused(session):
    sequence, samples, problems, live_ok, live_message = run_capture(
        list(straight_left_right()), live=False
    )
    assert sequence.done
    assert not problems  # embeddings still computed in observe mode
    assert not live_ok
    assert "not recognised as live" in live_message


def test_unmirrored_feed_also_completes():
    # Same physical movements, but the feed is not mirrored: image yaw signs are flipped.
    poses = [(-y, e) for (y, e) in straight_left_right()]
    sequence, samples, problems, live_ok, _ = run_capture(poses, mirrored=False)
    assert sequence.done
    assert not problems and live_ok
    assert len(samples) == 9


@pytest.mark.parametrize("cancel,existing", [(False, False), (True, False), (False, True), (True, True)])
def test_desktop_capture_main_selected_droidcam_and_atomic_save(session, monkeypatch, tmp_path, cancel, existing):
    from contextlib import contextmanager
    from types import SimpleNamespace
    import sys
    from app.vision import capture

    @contextmanager
    def local_session():
        yield session

    if existing:
        previous = Student(student_no="LOCAL-NEW", full_name="Original name", programme="Volunteer", level=100, fees_cleared=False, suspended=True)
        session.add(previous)
        session.flush()
        session.add_all([FaceEmbedding(student_id=previous.id, embedding=b"old", source_photo="capture:straight:0", det_score=1), FaceEmbedding(student_id=previous.id, embedding=b"phone", source_photo="web:straight:0", det_score=1)])
        session.commit()
    calls = []
    stopped = []
    counter = {"n": 0}
    class Reader:
        error = None
        def __init__(self, camera):
            pass
        def start(self):
            return self
        def read(self):
            counter["n"] += 1
            return counter["n"], np.zeros(SHAPE, dtype=np.uint8)
        def stop(self):
            stopped.append(True)

    def guide(frame):
        n = counter["n"]
        if n > 200:
            raise AssertionError("Guided capture did not complete")
        yaw = 0 if n <= 40 else -30 if n <= 90 else 30
        return [GuidedFace(bbox=(160, 120, 480, 360), score=0.95, pose=(0, yaw, 0), eye_ratio=0.3)]

    def model(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(guide=guide, embed=fake_embed())

    monkeypatch.setattr(capture, "engine", session.get_bind())
    monkeypatch.setattr(capture, "SessionLocal", local_session)
    monkeypatch.setattr(capture, "InsightFaceEmbedder", model)
    monkeypatch.setattr(capture, "open_camera", lambda *args: calls.append(args))
    monkeypatch.setattr(capture, "CameraReader", Reader)
    monkeypatch.setattr(capture.cv2, "imshow", lambda *args: None)
    monkeypatch.setattr(capture.cv2, "destroyAllWindows", lambda: None)
    monkeypatch.setattr(capture.cv2, "waitKey", lambda _: ord("q") if cancel else -1)
    monkeypatch.setattr(sys, "argv", ["capture", "--student-no=LOCAL-NEW", "--name=Local Volunteer", "--camera", "1", "--camera-source", "droidcam", "--capture-backend", "msmf", "--model", "buffalo_l", "--threads", "4"])
    capture.main()
    assert calls[0]["model_name"] == "buffalo_l"
    assert calls[1] == (1, "msmf", True)
    assert stopped
    person = session.scalar(select(Student).where(Student.student_no == "LOCAL-NEW"))
    if cancel and not existing:
        assert person is None
    else:
        assert person is not None
        rows = list(session.scalars(select(FaceEmbedding).where(FaceEmbedding.student_id == person.id)))
        captures = [row for row in rows if row.source_photo.startswith("capture:")]
        if existing:
            assert person.full_name == "Original name"
            assert not person.fees_cleared and person.suspended
            assert [row.embedding for row in rows if row.source_photo.startswith("web:")] == [b"phone"]
        if cancel:
            assert [row.embedding for row in captures] == [b"old"]
        else:
            assert len(captures) == 9
            assert all(row.embedding != b"old" for row in captures)
