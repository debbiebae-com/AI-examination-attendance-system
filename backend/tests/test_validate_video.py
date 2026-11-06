import json
from types import SimpleNamespace

import numpy as np
import pytest

from app.vision.validate_video import read_labels, score_frame, replay
from app.vision.matcher import FaceMatcher


def truth(identity, box=(0, 0, 20, 20)):
    return {"bbox": list(box), "student_no": identity}


def prediction(identity, state="confirmed", box=(0, 0, 20, 20)):
    return {**truth(identity, box), "state": state}


def labels_file(tmp_path, data):
    path = tmp_path / "labels.json"
    path.write_text(json.dumps(data))
    return path


def test_labels_allow_unknown_and_empty_frames(tmp_path):
    path = labels_file(tmp_path, {"frames": [{"frame": 0, "faces": [truth(None)]}, {"frame": 4, "faces": []}]})
    assert read_labels(path)[0][0]["student_no"] is None
    assert read_labels(path)[4] == []


@pytest.mark.parametrize("data", [
    {}, {"frames": []}, {"frames": [{"frame": -1, "faces": []}]},
    {"frames": [{"frame": 0, "faces": []}, {"frame": 0, "faces": []}]},
    {"frames": [{"frame": True, "faces": []}]},
    {"frames": [{"frame": 0, "faces": [{"bbox": [0, 0, 0, 10], "student_no": "A"}]}]},
    {"frames": [{"frame": 0, "faces": [{"bbox": [0, 0, 10, 10]}]}]},
])
def test_invalid_annotations_fail_before_processing(tmp_path, data):
    with pytest.raises(ValueError):
        read_labels(labels_file(tmp_path, data))


def test_scoring_distinguishes_correct_wrong_missing_and_unknown():
    pytest.importorskip("scipy")
    counts = score_frame([truth("A"), truth(None, (100, 0, 120, 20))],
                         [prediction("B"), prediction("A", box=(100, 0, 120, 20))])
    assert counts["known_wrong_identity"] == 1
    assert counts["unknown_false_accepts"] == 1
    missing = score_frame([truth("A"), truth(None, (100, 0, 120, 20))], [])
    assert missing["missed_face_detections"] == 2
    assert missing["known_not_identified"] == 1
    assert missing["unknown_correct_rejects"] == 0
    assert missing["unknown_unresolved"] == 1


@pytest.mark.parametrize("state,correct", [("unknown", 1), ("checking", 0), ("no_embedding", 0), ("untracked", 0), ("not_live", 0)])
def test_unresolved_faces_are_not_counted_as_successful_rejection(state, correct):
    pytest.importorskip("scipy")
    counts = score_frame([truth(None)], [prediction(None, state)])
    assert counts["unknown_correct_rejects"] == correct
    assert counts["unknown_unresolved"] == 1 - correct


def test_one_prediction_cannot_satisfy_two_labels():
    pytest.importorskip("scipy")
    counts = score_frame([truth("A"), truth("A")], [prediction("A")])
    assert counts["known_correct"] == 1
    assert counts["missed_face_detections"] == 1


def test_spatial_assignment_is_not_biased_towards_identity():
    pytest.importorskip("scipy")
    counts = score_frame([truth("A"), truth("B", (100, 0, 120, 20))],
                         [prediction("A", box=(100, 0, 120, 20)), prediction("B")])
    assert counts["known_wrong_identity"] == 2
    assert counts["known_correct"] == 0


def test_empty_labelled_frame_counts_extra_detection():
    pytest.importorskip("scipy")
    assert score_frame([], [prediction(None, "unknown")])["unlabelled_detections"] == 1


class FakeVideo:
    def __init__(self, frames=4):
        self.remaining = frames

    def read(self):
        if not self.remaining:
            return False, None
        self.remaining -= 1
        return True, np.zeros((100, 100, 3), dtype=np.uint8)


class FakeEmbedder:
    def analyse(self, image):
        return [SimpleNamespace(bbox=(80, 0, 100, 20), score=0.9, embedding=np.array([1., 0.]), is_live=None),
                SimpleNamespace(bbox=(0, 0, 20, 20), score=0.9, embedding=np.array([0., 1.]), is_live=None)]


def test_replay_uses_real_bytetrack_confirmation_and_mirrors_annotations():
    pytest.importorskip("supervision")
    matcher = FaceMatcher()
    matcher.enroll("PS/CSC/24/0016", np.array([1., 0.]))
    labels = {2: [truth("PS/CSC/24/0016"), truth(None, (80, 0, 100, 20))]}
    report = replay(FakeVideo(), FakeEmbedder(), matcher, labels)
    assert report["counts"]["known_correct"] == 1
    assert report["counts"]["unknown_correct_rejects"] == 1
    assert report["known_correct_rate"] == 1
    assert report["unknown_false_accept_rate"] == 0
    assert report["simulated_unique_marks"] == 1
    assert report["repeat_confirmations"] == 0
    assert report["attendance_database_writes"] == 0
    assert report["peak_detected_faces"] == 2
    assert report["processed_frames"] == 4
    assert report["mean_processing_ms"] >= 0


def test_unreachable_annotation_does_not_produce_misleading_report():
    pytest.importorskip("supervision")
    with pytest.raises(ValueError, match="never decoded"):
        replay(FakeVideo(), FakeEmbedder(), FaceMatcher(), {100: []})


def test_empty_video_fails():
    pytest.importorskip("supervision")
    with pytest.raises(ValueError, match="no readable"):
        replay(FakeVideo(0), FakeEmbedder(), FaceMatcher(), {0: []})


def test_cli_does_not_write_attendance_or_publish_live_feed(tmp_path, session, monkeypatch):
    pytest.importorskip("supervision")
    import cv2
    import sys
    from contextlib import nullcontext
    from sqlalchemy import event, select
    from app import db, live
    from app.models import FaceEmbedding, Student
    from app.vision import embedder as embedder_module
    from app.vision.validate_video import main

    student = session.scalar(select(Student).where(Student.student_no == "UGS-26-001"))
    session.add(FaceEmbedding(student_id=student.id, embedding=np.array([1., 0.], dtype=np.float32).tobytes(), source_photo="test", det_score=0.9))
    session.commit()
    writes = []
    def inspect_sql(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE", "CREATE", "DROP"}:
            writes.append(statement)
    event.listen(session.bind, "before_cursor_execute", inspect_sql)
    video = FakeVideo()
    video.isOpened = lambda: True
    video.release = lambda: None
    monkeypatch.setattr(cv2, "VideoCapture", lambda _: video)
    monkeypatch.setattr(db, "SessionLocal", lambda: nullcontext(session))
    monkeypatch.setattr(embedder_module, "InsightFaceEmbedder", lambda **kwargs: FakeEmbedder())
    def unexpected_publish(*args, **kwargs):
        raise AssertionError("Validation must not publish a live session")
    monkeypatch.setattr(live.LiveStore, "publish", unexpected_publish)
    annotation = labels_file(tmp_path, {"frames": [{"frame": 2, "faces": [truth("UGS-26-001")]}]})
    output = tmp_path / "report.json"
    monkeypatch.setattr(sys, "argv", ["validate_video", "--video", str(tmp_path / "input.mp4"),
                                     "--annotations", str(annotation), "--output", str(output)])
    try:
        main()
    finally:
        event.remove(session.bind, "before_cursor_execute", inspect_sql)
    assert writes == []
    assert json.loads(output.read_text())["counts"]["known_correct"] == 1
