"""Pins the InsightFace head-pose sign convention the capture driver depends on.

The driver converts image-space yaw to person space assuming: in an UNMIRRORED image,
positive yaw means the person turned towards their OWN left (nose moves to image-right).
This test reproduces that with the model's own mean 3D shape and pose code, so an upstream
change to the convention is caught here instead of silently flipping left/right again.

Skipped unless the vision extra (insightface) is installed.
"""

import math

import numpy as np
import pytest

pytest.importorskip("insightface")

from insightface.data import get_object  # noqa: E402
from insightface.utils import transform  # noqa: E402


def _pose_of(mean, pred):
    P = transform.estimate_affine_matrix_3d23d(mean, pred)
    _, R, _ = transform.P2sRt(P)
    return transform.matrix2angle(R)  # pitch, yaw, roll


def _rot_y(deg):
    th = math.radians(deg)
    return np.array([[math.cos(th), 0, math.sin(th)], [0, 1, 0], [-math.sin(th), 0, math.cos(th)]])


def test_positive_image_yaw_is_the_persons_own_left():
    mean = np.asarray(get_object("meanshape_68.pkl"), dtype=np.float64)
    center = mean.mean(axis=0)

    # Rotate the head so the nose tip moves towards image-right (+x). In an unmirrored
    # camera view that is the person turning towards their OWN left.
    pred = (_rot_y(25) @ (mean - center).T).T + center
    nose_dx = pred[30, 0] - center[0]
    assert nose_dx > 0  # nose moved to image-right

    _, yaw, _ = _pose_of(mean, pred)
    assert yaw > 15  # ...and the model reports it as POSITIVE yaw

    # The opposite turn is negative yaw.
    pred_left = (_rot_y(-25) @ (mean - center).T).T + center
    _, yaw_left, _ = _pose_of(mean, pred_left)
    assert yaw_left < -15


def test_driver_negates_yaw_only_for_mirrored_feeds():
    from app.vision.capture import to_signal
    from app.vision.embedder import GuidedFace

    shape = (480, 640, 3)
    # Person turns to their own left: model says +25 on an unmirrored feed, -25 mirrored.
    plain = to_signal([GuidedFace(bbox=(0, 0, 10, 10), score=0.9, pose=(0, 25, 0))], shape, mirrored=False)
    mirrored = to_signal([GuidedFace(bbox=(0, 0, 10, 10), score=0.9, pose=(0, -25, 0))], shape, mirrored=True)
    assert plain.yaw == pytest.approx(25.0)
    assert mirrored.yaw == pytest.approx(25.0)
