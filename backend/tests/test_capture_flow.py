import numpy as np
from sqlalchemy import select

from app.models import FaceEmbedding, Student
from app.vision.capture_flow import (
    CaptureSequence,
    FrameSignal,
    eye_aspect_ratio,
    mean_eye_ratio,
)
from app.vision.gallery import enroll_students, save_capture_samples


def emb(seed: int) -> np.ndarray:
    v = np.random.default_rng(seed).normal(size=512).astype(np.float32)
    return v / np.linalg.norm(v)


def frame(yaw=0.0, eye=0.3, live=True, faces=1, det=0.9, seed=1) -> FrameSignal:
    return FrameSignal(
        face_count=faces,
        det_score=det,
        is_live=live,
        yaw=yaw,
        eye_ratio=eye,
        embedding=emb(seed),
    )


def run_full_sequence(seq: CaptureSequence) -> None:
    for _ in range(3):
        seq.process(frame(yaw=0, seed=1))  # straight
    for _ in range(3):
        seq.process(frame(yaw=25, seed=2))  # left (with left_sign=1)
    for _ in range(3):
        seq.process(frame(yaw=-25, seed=3))  # right
    seq.process(frame(eye=0.3))  # eyes open, waiting for the blink
    seq.process(frame(eye=0.1))  # eyes closed
    seq.process(frame(eye=0.3, seed=4))  # eyes open again: blink complete


def test_eye_aspect_ratio_open_and_closed_eyes():
    open_eye = np.array([[0, 0], [1, -1], [2, -1], [3, 0], [2, 1], [1, 1]], dtype=np.float32)
    closed_eye = np.array([[0, 0], [1, -0.1], [2, -0.1], [3, 0], [2, 0.1], [1, 0.1]], dtype=np.float32)

    assert eye_aspect_ratio(open_eye) > 0.6
    assert eye_aspect_ratio(closed_eye) < 0.1


def test_mean_eye_ratio_uses_68_point_eye_positions():
    landmarks = np.zeros((68, 2), dtype=np.float32)
    landmarks[36:42] = [[0, 0], [1, -1], [2, -1], [3, 0], [2, 1], [1, 1]]  # right eye, open
    landmarks[42:48] = [[0, 0], [1, -0.1], [2, -0.1], [3, 0], [2, 0.1], [1, 0.1]]  # left eye, closed

    ratio = mean_eye_ratio(landmarks)

    assert 0.3 < ratio < 0.4


def test_full_sequence_completes_and_collects_samples():
    seq = CaptureSequence(gap_frames=0)
    run_full_sequence(seq)

    assert seq.done
    assert len(seq.samples) == 3 + 3 + 3 + 1
    assert [s.step for s in seq.samples] == ["straight"] * 3 + ["left"] * 3 + ["right"] * 3 + ["blink"]


def test_left_sign_flips_which_direction_counts_as_left():
    seq = CaptureSequence(left_sign=-1, gap_frames=0)
    for _ in range(3):
        seq.process(frame(yaw=0))
    # With left_sign=-1 a negative yaw is a turn to the person's left.
    for _ in range(3):
        assert seq.process(frame(yaw=-25)) == ""
    assert seq.current_step == "right"


def test_turning_the_wrong_way_does_not_advance():
    seq = CaptureSequence(gap_frames=0)
    for _ in range(3):
        seq.process(frame(yaw=0))
    assert seq.current_step == "left"
    message = seq.process(frame(yaw=-25))  # wrong direction for "left"
    assert message == "Turn a little further to your left"
    assert seq.progress("left") == (0, 3)


def test_photo_or_screen_is_never_accepted():
    seq = CaptureSequence(gap_frames=0)
    message = seq.process(frame(yaw=0, live=False))
    assert "not recognised as live" in message
    assert seq.progress("straight") == (0, 3)


def test_two_people_in_view_is_refused():
    seq = CaptureSequence(gap_frames=0)
    assert seq.process(frame(faces=2)) == "Only one person should be in view"
    assert seq.progress("straight") == (0, 3)


def test_no_face_is_refused():
    seq = CaptureSequence(gap_frames=0)
    assert seq.process(FrameSignal(face_count=0)) == "No face found"


def test_blink_requires_eyes_to_close_and_reopen():
    seq = CaptureSequence(gap_frames=0)
    for _ in range(3):
        seq.process(frame(yaw=0))
    for _ in range(3):
        seq.process(frame(yaw=25))
    for _ in range(3):
        seq.process(frame(yaw=-25))
    assert seq.current_step == "blink"

    # Eyes staying open is not a blink.
    seq.process(frame(eye=0.3))
    seq.process(frame(eye=0.32))
    assert seq.current_step == "blink"

    seq.process(frame(eye=0.1))
    seq.process(frame(eye=0.3))
    assert seq.done


def test_gap_frames_stop_one_pose_being_stored_many_times():
    seq = CaptureSequence(gap_frames=5, samples_per_step=3)
    results = [seq.process(frame(yaw=0)) for _ in range(6)]

    # Six identical frames with a gap of 5 keep two samples: the first frame and the sixth.
    assert seq.progress("straight") == (2, 3)
    assert results.count("") == 6


def test_capture_samples_survive_photo_reenrollment(session):
    student = session.scalar(select(Student).where(Student.student_no == "UGS-26-001"))
    seq = CaptureSequence(gap_frames=0)
    run_full_sequence(seq)
    save_capture_samples(session, student.id, seq.samples)

    class NoPhotoFaces:
        def detect(self, path):
            return []

    enroll_students(session, NoPhotoFaces())

    remaining = session.scalars(select(FaceEmbedding).where(FaceEmbedding.student_id == student.id)).all()
    assert len(remaining) == len(seq.samples)


def test_saving_capture_again_replaces_previous_capture(session):
    student = session.scalar(select(Student).where(Student.student_no == "UGS-26-001"))
    seq = CaptureSequence(gap_frames=0)
    run_full_sequence(seq)

    save_capture_samples(session, student.id, seq.samples)
    save_capture_samples(session, student.id, seq.samples)

    rows = session.scalars(select(FaceEmbedding).where(FaceEmbedding.student_id == student.id)).all()
    assert len(rows) == len(seq.samples)
