"""Guided face capture: prompts (look straight, turn left, turn right, blink) that keep only good frames.

This is pure logic with no camera or model dependency, so it is unit tested. capture.py drives it.
"""

from dataclasses import dataclass

import numpy as np

STEPS = ("straight", "left", "right", "blink")
PROMPTS = {
    "straight": "Look straight at the camera",
    "left": "Slowly turn your head to your LEFT",
    "right": "Slowly turn your head to your RIGHT",
    "blink": "Blink once",
}

# Starting values. Tune them on your PC: the capture window shows live yaw and eye values.
STRAIGHT_MAX_DEG = 12.0  # |yaw| below this counts as facing the camera
TURN_MIN_DEG = 20.0  # turned at least this far counts as a turn
EYE_OPEN = 0.24  # eye aspect ratio above this is open
EYE_CLOSED = 0.19  # eye aspect ratio below this is closed
MIN_DET_SCORE = 0.6
DEFAULT_SAMPLES = 3  # frames kept for each turn or straight step
DEFAULT_GAP_FRAMES = 5  # minimum frames between kept samples, so one pose is not stored many times


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
    """What the camera pipeline reports about one frame."""

    face_count: int
    det_score: float = 0.0
    is_live: bool | None = None  # None when liveness is not checked
    yaw: float | None = None  # degrees; sign depends on the camera (see left_sign)
    eye_ratio: float | None = None
    embedding: np.ndarray | None = None


@dataclass(frozen=True)
class Sample:
    step: str
    index: int
    embedding: np.ndarray
    det_score: float


def _frame_problem(frame: FrameSignal) -> str:
    if frame.face_count == 0:
        return "No face found"
    if frame.face_count > 1:
        return "Only one person should be in view"
    if frame.is_live is False:
        return "Face not recognised as live. Use your real face, not a photo or screen"
    if frame.det_score < MIN_DET_SCORE:
        return "Face not clear enough. Improve the light and move closer"
    if frame.embedding is None:
        return "Could not read the face. Try again"
    return ""


class CaptureSequence:
    """Walks one person through the prompts and collects embeddings for each step."""

    def __init__(
        self,
        *,
        left_sign: int = 1,
        samples_per_step: int = DEFAULT_SAMPLES,
        gap_frames: int = DEFAULT_GAP_FRAMES,
    ):
        if left_sign not in (1, -1):
            raise ValueError("left_sign must be 1 or -1")
        self.left_sign = left_sign
        self.gap_frames = gap_frames
        self.needed = {step: samples_per_step for step in STEPS}
        self.needed["blink"] = 1
        self.samples: list[Sample] = []
        self._step_index = 0
        self._counts = {step: 0 for step in STEPS}
        self._frames_since_keep = gap_frames
        self._blink_closed_seen = False

    @property
    def current_step(self) -> str | None:
        return STEPS[self._step_index] if self._step_index < len(STEPS) else None

    @property
    def done(self) -> bool:
        return self.current_step is None

    def progress(self, step: str) -> tuple[int, int]:
        return self._counts[step], self.needed[step]

    def process(self, frame: FrameSignal) -> str:
        """Process one frame. Returns guidance for the user, or '' when the frame was accepted."""
        step = self.current_step
        if step is None:
            return "Capture complete"
        self._frames_since_keep += 1

        problem = _frame_problem(frame)
        if problem:
            return problem

        if step == "blink":
            return self._process_blink(frame)

        if frame.yaw is None:
            return "Head angle not available"
        turned = self.left_sign * frame.yaw  # positive means the person's head is turned to their left

        if step == "straight" and abs(frame.yaw) > STRAIGHT_MAX_DEG:
            return "Face the camera directly"
        if step == "left" and turned < TURN_MIN_DEG:
            return "Turn a little further to your left"
        if step == "right" and turned > -TURN_MIN_DEG:
            return "Turn a little further to your right"

        if self._frames_since_keep < self.gap_frames:
            return ""
        self._keep(step, frame)
        return ""

    def _process_blink(self, frame: FrameSignal) -> str:
        if frame.eye_ratio is None:
            return "Eyes not visible"
        if not self._blink_closed_seen:
            if frame.eye_ratio <= EYE_CLOSED:
                self._blink_closed_seen = True
                return "Now open your eyes"
            return PROMPTS["blink"]
        if frame.eye_ratio >= EYE_OPEN:
            self._keep("blink", frame)
            return ""
        return "Open your eyes"

    def _keep(self, step: str, frame: FrameSignal) -> None:
        self.samples.append(Sample(step, self._counts[step], frame.embedding, frame.det_score))
        self._counts[step] += 1
        self._frames_since_keep = 0
        if self._counts[step] >= self.needed[step]:
            self._step_index += 1
            self._blink_closed_seen = False
