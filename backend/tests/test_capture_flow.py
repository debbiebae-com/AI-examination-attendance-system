import numpy as np
from sqlalchemy import select

from app.models import FaceEmbedding, Student
from app.vision.capture_flow import (
    CaptureSequence,
    FrameSignal,
    eye_aspect_ratio,
    liveness_summary,
    mean_eye_ratio,
    missing_steps,
)
from app.vision.gallery import enroll_students, save_capture_samples


def emb(seed: int) -> np.ndarray:
    v = np.random.default_rng(seed).normal(size=512).astype(np.float32)
    return v / np.linalg.norm(v)


def frame(yaw=0.0, eye=0.3, faces=1, det=0.9, **box) -> FrameSignal:
    return FrameSignal(face_count=faces, det_score=det, yaw=yaw, eye_ratio=eye, **box)


def advance(seq: CaptureSequence, yaw: float, eye: float = 0.3, cap: int = 80) -> int:
    """Feed frames at a fixed pose until the current step advances. Returns frames used."""
    start = seq.current_step
    for i in range(cap):
        seq.process(frame(yaw=yaw, eye=eye))
        if seq.current_step != start:
            return i + 1
    raise AssertionError(f"step {start!r} did not advance within {cap} frames")


def run_full_sequence(seq: CaptureSequence) -> None:
    advance(seq, yaw=0)  # straight (person space)
    advance(seq, yaw=30)  # left: positive yaw is the person's own left
    advance(seq, yaw=-30)  # right
    seq.process(frame(eye=0.3))  # eyes open, waiting for the blink
    seq.process(frame(eye=0.03))  # eyes closed
    seq.process(frame(eye=0.3))  # eyes open again: blink complete


def sample(step, index, seed):
    from app.vision.capture_flow import Sample

    return Sample(step, index, emb(seed), 0.9)


# -- eye geometry ----------------------------------------------------------


def test_eye_aspect_ratio_open_and_closed_eyes():
    open_eye = np.array([[0, 0], [1, -1], [2, -1], [3, 0], [2, 1], [1, 1]], dtype=np.float32)
    closed_eye = np.array([[0, 0], [1, -0.1], [2, -0.1], [3, 0], [2, 0.1], [1, 0.1]], dtype=np.float32)
    assert eye_aspect_ratio(open_eye) > 0.6
    assert eye_aspect_ratio(closed_eye) < 0.1


def test_mean_eye_ratio_uses_68_point_eye_positions():
    landmarks = np.zeros((68, 2), dtype=np.float32)
    landmarks[36:42] = [[0, 0], [1, -1], [2, -1], [3, 0], [2, 1], [1, 1]]
    landmarks[42:48] = [[0, 0], [1, -0.1], [2, -0.1], [3, 0], [2, 0.1], [1, 0.1]]
    assert 0.3 < mean_eye_ratio(landmarks) < 0.4


# -- full sequence in person space ----------------------------------------


def test_full_sequence_completes_and_collects_samples():
    seq = CaptureSequence(gap_frames=0)
    run_full_sequence(seq)
    assert seq.done
    assert len(seq.accepted_frames) == 3 + 3 + 3 + 1
    assert [f.step for f in seq.accepted_frames] == ["straight"] * 3 + ["left"] * 3 + ["right"] * 3 + ["blink"]


def test_left_is_positive_person_space_yaw():
    seq = CaptureSequence(gap_frames=0)
    advance(seq, yaw=0)
    assert seq.current_step == "left"
    # Turning to the person's own LEFT is positive yaw and must complete the step.
    advance(seq, yaw=30)
    assert seq.current_step == "right"


def test_turning_the_wrong_way_gives_an_explicit_correction():
    seq = CaptureSequence(gap_frames=0)
    advance(seq, yaw=0)
    assert seq.current_step == "left"
    verdict = seq.process(frame(yaw=-30))  # turning right during the left step
    assert "RIGHT" in verdict.message and "LEFT" in verdict.message
    assert verdict.accepted is None
    assert seq.progress("left") == (0, 3)


def test_right_step_corrects_a_left_turn():
    seq = CaptureSequence(gap_frames=0)
    advance(seq, yaw=0)
    advance(seq, yaw=30)
    assert seq.current_step == "right"
    verdict = seq.process(frame(yaw=30))  # still turned left during the right step
    assert "LEFT" in verdict.message and "RIGHT" in verdict.message
    assert seq.progress("right") == (0, 3)


# -- frame quality ---------------------------------------------------------


def test_two_people_in_view_is_refused():
    seq = CaptureSequence(gap_frames=0)
    assert seq.process(frame(faces=2)).message == "Only one person should be in view"
    assert seq.progress("straight") == (0, 3)


def test_no_face_is_refused():
    seq = CaptureSequence(gap_frames=0)
    assert seq.process(FrameSignal(face_count=0)).message == "No face found. Look at the camera"


def test_low_detection_score_is_refused():
    seq = CaptureSequence(gap_frames=0)
    assert "not clear enough" in seq.process(frame(det=0.3)).message


def test_face_too_small_or_off_center_gets_guidance():
    seq = CaptureSequence(gap_frames=0)
    assert "closer" in seq.process(frame(face_w=0.10, face_cx=0.5, face_cy=0.5)).message
    assert "back" in seq.process(frame(face_w=0.80, face_cx=0.5, face_cy=0.5)).message
    assert "Center" in seq.process(frame(face_w=0.3, face_cx=0.9, face_cy=0.5)).message
    assert seq.progress("straight") == (0, 3)


# -- blink -----------------------------------------------------------------


def test_blink_requires_eyes_to_close_and_reopen():
    seq = CaptureSequence(gap_frames=0)
    advance(seq, yaw=0)
    advance(seq, yaw=30)
    advance(seq, yaw=-30)
    assert seq.current_step == "blink"

    seq.process(frame(eye=0.3))
    seq.process(frame(eye=0.32))
    assert seq.current_step == "blink"  # staying open is not a blink

    seq.process(frame(eye=0.03))
    seq.process(frame(eye=0.3))
    assert seq.done


def test_blink_calibrates_for_small_eyes():
    # A person whose OPEN eyes read only 0.16 (below the old fixed closed threshold).
    seq = CaptureSequence(gap_frames=0)
    advance(seq, yaw=0, eye=0.16)
    advance(seq, yaw=30, eye=0.16)
    advance(seq, yaw=-30, eye=0.16)
    assert seq.current_step == "blink"
    assert seq.eye_baseline is not None and seq.eye_baseline < 0.19

    # Their normal open eyes must NOT be mistaken for a blink.
    seq.process(frame(eye=0.16))
    assert seq.current_step == "blink"
    # A real close then reopen completes it.
    seq.process(frame(eye=0.03))
    seq.process(frame(eye=0.16))
    assert seq.done


def test_blink_calibrates_for_large_eyes():
    seq = CaptureSequence(gap_frames=0)
    advance(seq, yaw=0, eye=0.36)
    advance(seq, yaw=30, eye=0.36)
    advance(seq, yaw=-30, eye=0.36)
    assert seq.current_step == "blink"
    # A shallow dip is not a full blink for someone with wide-open eyes.
    seq.process(frame(eye=0.24))
    seq.process(frame(eye=0.36))
    assert seq.current_step == "blink"
    seq.process(frame(eye=0.05))
    seq.process(frame(eye=0.36))
    assert seq.done


# -- smoothing and spacing -------------------------------------------------


def test_smoothing_rejects_a_single_noisy_frame():
    seq = CaptureSequence(gap_frames=0)
    advance(seq, yaw=0)
    assert seq.current_step == "left"
    # One noisy spike to the right should not trigger the wrong-way correction.
    seq.process(frame(yaw=20))  # start turning left
    verdict = seq.process(frame(yaw=-15))  # single noisy frame
    assert "RIGHT" not in verdict.message


def test_gap_frames_stop_one_pose_being_stored_many_times():
    seq = CaptureSequence(gap_frames=5, samples_per_step=3)
    for _ in range(6):
        seq.process(frame(yaw=0))
    # Six identical frames with a gap of 5 keep two samples: the first and the sixth.
    assert seq.progress("straight") == (2, 3)


# -- finishing helpers -----------------------------------------------------


def test_liveness_summary_passes_on_a_clear_majority():
    ok, message = liveness_summary([True, True, False, True, None])
    assert ok and message == ""


def test_liveness_summary_fails_on_mostly_not_live():
    ok, message = liveness_summary([False, False, True, False])
    assert not ok and "not recognised as live" in message


def test_liveness_summary_fails_when_nothing_scored():
    ok, message = liveness_summary([None, None])
    assert not ok and "could not be checked" in message


def test_missing_steps_reports_absent_poses():
    samples = [sample("straight", 0, 1), sample("left", 0, 2), sample("blink", 0, 3)]
    assert missing_steps(samples) == ["right"]


# -- persistence -----------------------------------------------------------


def _samples_from_sequence(seq):
    from app.vision.capture_flow import Sample

    return [Sample(f.step, f.index, emb(i + 1), f.det_score) for i, f in enumerate(seq.accepted_frames)]


def test_capture_samples_survive_photo_reenrollment(session):
    student = session.scalar(select(Student).where(Student.student_no == "UGS-26-001"))
    seq = CaptureSequence(gap_frames=0)
    run_full_sequence(seq)
    samples = _samples_from_sequence(seq)
    save_capture_samples(session, student.id, samples)

    class NoPhotoFaces:
        def detect(self, path):
            return []

    enroll_students(session, NoPhotoFaces())
    remaining = session.scalars(select(FaceEmbedding).where(FaceEmbedding.student_id == student.id)).all()
    assert len(remaining) == len(samples)


def test_saving_capture_again_replaces_previous_capture(session):
    student = session.scalar(select(Student).where(Student.student_no == "UGS-26-001"))
    seq = CaptureSequence(gap_frames=0)
    run_full_sequence(seq)
    samples = _samples_from_sequence(seq)
    save_capture_samples(session, student.id, samples)
    save_capture_samples(session, student.id, samples)
    rows = session.scalars(select(FaceEmbedding).where(FaceEmbedding.student_id == student.id)).all()
    assert len(rows) == len(samples)
