"""Guided face capture: prompts (look straight, turn left, turn right) that keep only good frames.

This is pure logic with no camera or model dependency, so it is unit tested. capture.py drives it.

Conventions
-----------
* ``yaw`` is in PERSON space: positive means the person has turned towards their OWN left.
  The camera driver converts the model's image-space yaw into person space (a mirrored
  preview flips the sign), so this module never has to guess the camera's orientation.
* Acceptance is based on pose and image quality only. The heavy face embedding and the
  passive liveness check run on the few kept frames, not on every camera frame, and the
  liveness verdict is aggregated over the whole capture (see ``liveness_summary``).

Liveness comes from the turn challenge (a photo or screen cannot turn its head) plus the
passive liveness model. There is no blink step.
"""

from collections import Counter
from dataclasses import dataclass

import numpy as np

STEPS = ("straight", "left", "right")
PROMPTS = {
    "straight": "Look straight at the camera",
    "left": "Slowly turn your head to your LEFT",
    "right": "Slowly turn your head to your RIGHT",
}

# Pose windows (degrees, person space). Generous on purpose: the challenge-response
# itself is the liveness proof, so we do not need extreme angles.
STRAIGHT_MAX_DEG = 15.0  # |yaw| below this counts as facing the camera
TURN_MIN_DEG = 18.0  # turned at least this far counts as a turn
WRONG_WAY_DEG = 8.0  # turned the other way past this -> explicit correction message
MIN_DET_SCORE = 0.5

# Normalised face-box guidance. Keeps the face large and central enough that the
# liveness crop is not rejected for missing image area around the face.
MIN_FACE_W = 0.16
MAX_FACE_W = 0.62
FACE_CX_RANGE = (0.28, 0.72)
FACE_CY_RANGE = (0.22, 0.78)

DEFAULT_SAMPLES = 3  # frames kept for each turn or straight step
DEFAULT_GAP_FRAMES = 6  # minimum frames between kept samples, so one pose is not stored many times
YAW_EMA_ALPHA = 0.4  # smoothing for the head angle, so a single noisy frame does not stall a step

EYE_FLOOR = 0.05  # absolute "fully closed" floor; skip closed-eye reference frames (person-independent)


def eye_aspect_ratio(eye: np.ndarray) -> float:
    """Eye openness from six points, ordered: outer corner, upper, upper, inner corner, lower, lower."""
    points = np.asarray(eye, dtype=np.float32)[:, :2]
    horizontal = float(np.linalg.norm(points[0] - points[3]))
    if horizontal == 0.0:
        return 0.0
    vertical = float(np.linalg.norm(points[1] - points[5]) + np.linalg.norm(points[2] - points[4]))
    return vertical / (2.0 * horizontal)


def mean_eye_ratio(landmarks_68: np.ndarray) -> float:
    """Average eye openness for the standard 68-point layout: subject's right eye 36-41, left eye 42-47."""
    right = eye_aspect_ratio(landmarks_68[36:42])
    left = eye_aspect_ratio(landmarks_68[42:48])
    return (right + left) / 2.0


@dataclass(frozen=True)
class FrameSignal:
    """What the camera pipeline reports about one frame, already in person space."""

    face_count: int
    det_score: float = 0.0
    yaw: float | None = None  # degrees; positive = turned towards the person's own left
    eye_ratio: float | None = None
    # Normalised face box (centre x, centre y, width), each 0..1. Optional quality guidance.
    face_cx: float | None = None
    face_cy: float | None = None
    face_w: float | None = None


@dataclass(frozen=True)
class Verdict:
    """Result of processing one frame."""

    message: str = ""  # guidance for the user; empty when the frame is good
    accepted: str | None = None  # step name when this frame should be kept and embedded


@dataclass(frozen=True)
class AcceptedFrame:
    """A frame the sequence accepted. The driver embeds it and joins the result back by (step, index)."""

    step: str
    index: int
    det_score: float


@dataclass(frozen=True)
class Sample:
    step: str
    index: int
    embedding: np.ndarray
    det_score: float


def _box_problem(signal: FrameSignal) -> str:
    if signal.face_w is not None:
        if signal.face_w < MIN_FACE_W:
            return "Move a little closer to the camera"
        if signal.face_w > MAX_FACE_W:
            return "Move back a little"
    if signal.face_cx is not None and not FACE_CX_RANGE[0] <= signal.face_cx <= FACE_CX_RANGE[1]:
        return "Center your face in the frame"
    if signal.face_cy is not None and not FACE_CY_RANGE[0] <= signal.face_cy <= FACE_CY_RANGE[1]:
        return "Center your face in the frame"
    return ""


def _frame_problem(signal: FrameSignal) -> str:
    if signal.face_count == 0:
        return "No face found. Look at the camera"
    if signal.face_count > 1:
        return "Only one person should be in view"
    if signal.det_score < MIN_DET_SCORE:
        return "Face not clear enough. Improve the light"
    return _box_problem(signal)


class CaptureSequence:
    """Walks one person through the prompts and decides which frames to keep.

    Yaw arrives in person space (positive = the person's own left), so there is no
    camera-sign flag to get wrong. The head angle is smoothed so a single noisy frame
    does not stall a step.
    """

    def __init__(
        self,
        *,
        samples_per_step: int = DEFAULT_SAMPLES,
        gap_frames: int = DEFAULT_GAP_FRAMES,
    ):
        if samples_per_step < 1:
            raise ValueError("samples_per_step must be at least 1")
        self.gap_frames = gap_frames
        self.needed = {step: samples_per_step for step in STEPS}
        self.accepted_frames: list[AcceptedFrame] = []
        self._step_index = 0
        self._counts = {step: 0 for step in STEPS}
        self._frames_since_keep = gap_frames
        self._yaw_ema: float | None = None

    @property
    def current_step(self) -> str | None:
        return STEPS[self._step_index] if self._step_index < len(STEPS) else None

    @property
    def done(self) -> bool:
        return self.current_step is None

    @property
    def smoothed_yaw(self) -> float | None:
        return self._yaw_ema

    def progress(self, step: str) -> tuple[int, int]:
        return self._counts[step], self.needed[step]

    def process(self, signal: FrameSignal) -> Verdict:
        """Process one frame. Returns guidance and, when a frame is kept, the step it belongs to."""
        step = self.current_step
        if step is None:
            return Verdict("Capture complete")
        self._frames_since_keep += 1

        problem = _frame_problem(signal)
        if problem:
            return Verdict(problem)

        if signal.yaw is not None:
            self._yaw_ema = (
                signal.yaw if self._yaw_ema is None else YAW_EMA_ALPHA * signal.yaw + (1 - YAW_EMA_ALPHA) * self._yaw_ema
            )
        yaw = self._yaw_ema

        if yaw is None:
            return Verdict("Head angle not available. Improve the light")

        if step == "straight":
            if abs(yaw) > STRAIGHT_MAX_DEG:
                return Verdict("Face the camera directly")
            if signal.eye_ratio is not None and signal.eye_ratio < EYE_FLOOR:
                return Verdict("Open your eyes")
        elif step == "left":
            if yaw < -WRONG_WAY_DEG:
                return Verdict("That's your RIGHT. Turn to your LEFT")
            if yaw < TURN_MIN_DEG:
                return Verdict("Turn a little further to your left")
        elif step == "right":
            if yaw > WRONG_WAY_DEG:
                return Verdict("That's your LEFT. Turn to your RIGHT")
            if yaw > -TURN_MIN_DEG:
                return Verdict("Turn a little further to your right")

        if self._frames_since_keep < self.gap_frames:
            return Verdict("")
        return Verdict("", accepted=self._keep(step, signal))

    def _keep(self, step: str, signal: FrameSignal) -> str:
        index = self._counts[step]
        self.accepted_frames.append(AcceptedFrame(step, index, signal.det_score))
        self._counts[step] += 1
        self._frames_since_keep = 0
        if self._counts[step] >= self.needed[step]:
            self._step_index += 1
        return step


# -- finishing helpers (pure, unit tested) ---------------------------------


def liveness_summary(flags: list[bool | None]) -> tuple[bool, str]:
    """Aggregate the passive liveness votes over the kept frames.

    The turn challenge is the active liveness proof; the passive model is noisy frame
    to frame, so a clear majority of live votes passes the capture instead of requiring
    every single frame to be live.
    """
    scored = [flag for flag in flags if flag is not None]
    if not scored:
        return False, "Liveness could not be checked. Keep your face fully in view and try again"
    live = sum(1 for flag in scored if flag)
    if live / len(scored) >= 0.6:
        return True, ""
    return False, "Face not recognised as live. Use your real face, not a photo or screen"


def missing_steps(samples: list[Sample]) -> list[str]:
    """Steps that ended up with no usable sample (e.g. an embedding failed)."""
    counts = Counter(sample.step for sample in samples)
    return [step for step in STEPS if counts.get(step, 0) == 0]
