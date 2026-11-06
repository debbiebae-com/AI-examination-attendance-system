"""Live recognition decisions: follow each face across frames and decide when to record attendance.

No camera or database dependency. Tracking uses Supervision ByteTrack (vision extra).
"""

from dataclasses import dataclass

Box = tuple[float, float, float, float]  # x1, y1, x2, y2

CONFIRM_FRAMES = 3  # consecutive frames a face must match the same student before attendance is recorded
MAX_MISSED_FRAMES = 10  # frames a face can be out of view before it is forgotten


def iou(a: Box, b: Box) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if intersection == 0.0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return intersection / (area_a + area_b - intersection)


@dataclass
class _Track:
    track_id: int
    box: Box
    missed: int = 0
    candidate: str | None = None
    streak: int = 0
    marked: bool = False
    label: str = "checking"


class FaceTracker:
    """ByteTrack adapter preserving recognition state independently of motion state.

    Supervision provides Kalman prediction and high/low confidence association.
    Unconfirmed detections return None; never invent IDs for rejected detections.
    Imports stay lazy so the API can run without the optional vision extra.
    """

    def __init__(self, max_missed: int = MAX_MISSED_FRAMES,
                 activation_threshold: float = 0.5):
        import supervision as sv

        self.max_missed = max_missed
        self._sv = sv
        self._tracker = sv.ByteTrack(
            track_activation_threshold=activation_threshold,
            lost_track_buffer=max_missed,
            frame_rate=30,  # buffer measured in processed updates, not camera FPS
            minimum_consecutive_frames=1,
        )
        self._tracks: dict[int, _Track] = {}

    @property
    def ids(self) -> list[int]:
        return list(self._tracks)

    def track(self, track_id: int) -> _Track:
        return self._tracks[track_id]

    def update(self, boxes: list[Box], scores: list[float] | None = None) -> list[int | None]:
        """Return one optional ID per input face, retaining its original order.

        Detection scores, not recognition similarities, drive ByteTrack association.
        Missing scores are for synthetic tests only; the camera passes SCRFD scores.
        """
        import numpy as np

        if scores is None:
            scores = [1.0] * len(boxes)
        if len(scores) != len(boxes):
            raise ValueError("One detection score is required per box")
        detections = self._sv.Detections(
            xyxy=np.asarray(boxes, dtype=np.float32).reshape(-1, 4),
            confidence=np.asarray(scores, dtype=np.float32),
            data={"input_index": np.arange(len(boxes))},
        )
        tracked = self._tracker.update_with_detections(detections)
        ids: list[int | None] = [None] * len(boxes)
        for track in self._tracks.values():
            track.missed += 1
        for index, tid in zip(tracked.data.get("input_index", []), tracked.tracker_id):
            index, tid = int(index), int(tid)
            ids[index] = tid
            if tid not in self._tracks:
                self._tracks[tid] = _Track(track_id=tid, box=boxes[index])
            track = self._tracks[tid]
            if track.missed > 1:
                # A gap breaks consecutive recognition evidence, even if motion
                # tracking correctly recovers the same ID after occlusion.
                AttendanceDecider._reset(track, "checking")
            track.box = boxes[index]
            track.missed = 0
        for tid in list(self._tracks):
            if self._tracks[tid].missed:
                AttendanceDecider._reset(self._tracks[tid], "checking")
            if self._tracks[tid].missed > self.max_missed:
                del self._tracks[tid]
        return ids


@dataclass(frozen=True)
class Decision:
    action: str  # "checking", "confirmed", "marked", "unknown", "not_live"
    student_no: str | None = None


class AttendanceDecider:
    """Decides, per tracked face, when a recognised student should be recorded as present."""

    def __init__(self, tracker: FaceTracker, confirm_frames: int = CONFIRM_FRAMES):
        if confirm_frames < 1:
            raise ValueError("confirm_frames must be positive")
        self.tracker = tracker
        self.confirm_frames = confirm_frames

    def observe(self, track_id: int, *, is_live: bool | None, student_no: str | None) -> Decision:
        track = self.tracker.track(track_id)

        if is_live is False:
            self._reset(track, "not live")
            return Decision("not_live")

        if student_no is None:
            self._reset(track, "unknown")
            return Decision("unknown")

        if track.marked and student_no == track.candidate:
            return Decision("marked", track.candidate)

        if student_no == track.candidate:
            track.streak += 1
        else:
            track.marked = False
            track.candidate = student_no
            track.streak = 1

        if track.streak >= self.confirm_frames:
            track.marked = True
            return Decision("confirmed", student_no)

        track.label = f"checking {track.streak}/{self.confirm_frames}"
        return Decision("checking", student_no)

    def set_label(self, track_id: int, label: str) -> None:
        self.tracker.track(track_id).label = label

    @staticmethod
    def _reset(track: _Track, label: str) -> None:
        track.marked = False
        track.candidate = None
        track.streak = 0
        track.label = label
