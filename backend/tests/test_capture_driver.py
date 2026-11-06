"""Driver-level tests: the person-space yaw mapping (the left/right fix) and the overlay.

These need OpenCV, so they are skipped when the vision extra is not installed.
"""

import numpy as np
import pytest

pytest.importorskip("cv2")

from app.vision.capture import draw_overlay, to_signal  # noqa: E402
from app.vision.capture_flow import CaptureSequence, FrameSignal  # noqa: E402
from app.vision.embedder import GuidedFace  # noqa: E402

SHAPE = (480, 640, 3)


def guided(yaw_image, bbox=(160, 120, 480, 360)):
    return GuidedFace(bbox=bbox, score=0.9, pose=(0.0, yaw_image, 0.0), eye_ratio=0.3)


def test_mirrored_preview_maps_person_left_to_positive_yaw():
    # In a MIRRORED image the model reports NEGATIVE yaw when the person turns to their
    # own left. The driver must negate it so person space stays positive-left.
    signal = to_signal([guided(yaw_image=-25)], SHAPE, mirrored=True)
    assert signal.yaw == pytest.approx(25.0)


def test_unmirrored_preview_keeps_person_left_positive():
    # In an UNMIRRORED image the model already reports positive yaw for the person's left.
    signal = to_signal([guided(yaw_image=25)], SHAPE, mirrored=False)
    assert signal.yaw == pytest.approx(25.0)


def test_mirrored_right_turn_is_negative_person_yaw():
    signal = to_signal([guided(yaw_image=25)], SHAPE, mirrored=True)
    assert signal.yaw == pytest.approx(-25.0)


def test_person_space_mapping_is_consistent_across_mirror_modes():
    # The same physical turn (person's left) must give the same person-space yaw whether
    # the feed is mirrored or not — that is the whole point of the conversion.
    mirrored = to_signal([guided(yaw_image=-30)], SHAPE, mirrored=True)
    plain = to_signal([guided(yaw_image=30)], SHAPE, mirrored=False)
    assert mirrored.yaw == pytest.approx(plain.yaw)


def test_face_box_is_normalised():
    signal = to_signal([guided(0, bbox=(100, 100, 300, 300))], SHAPE, mirrored=True)
    assert signal.face_cx == pytest.approx(200 / 640)
    assert signal.face_cy == pytest.approx(200 / 480)
    assert signal.face_w == pytest.approx(200 / 640)


def test_multiple_and_zero_faces():
    assert to_signal([guided(0), guided(0)], SHAPE, mirrored=True).face_count == 2
    assert to_signal([], SHAPE, mirrored=True).face_count == 0


def test_overlay_draws_without_error_for_every_step():
    import cv2

    for target_yaw, step in [(0, "straight"), (30, "left"), (-30, "right")]:
        seq = CaptureSequence(gap_frames=0)
        # Drive the sequence to the desired step.
        from tests.test_capture_flow import advance

        if step in ("left", "right"):
            advance(seq, yaw=0)
        if step == "right":
            advance(seq, yaw=30)
        image = np.zeros(SHAPE, dtype=np.uint8)
        signal = FrameSignal(face_count=1, det_score=0.9, yaw=target_yaw, eye_ratio=0.3)
        for mirrored in (True, False):
            draw_overlay(image.copy(), [guided(0)], seq, "guide text", signal, 30.0, mirrored, 0.0)
    # Done state too.
    seq = CaptureSequence(gap_frames=0)
    from tests.test_capture_flow import run_full_sequence

    run_full_sequence(seq)
    draw_overlay(np.zeros(SHAPE, np.uint8), [], seq, "", FrameSignal(face_count=0), 30.0, True, 0.0)
