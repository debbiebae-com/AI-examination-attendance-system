"""Live recognition decisions: follow each face across frames and decide when to record attendance.

Pure logic with no camera or database dependency, so it is unit tested. attend.py drives it.
"""

from dataclasses import dataclass

Box = tuple[float, float, float, float]  # x1, y1, x2, y2

CONFIRM_FRAMES = 3  # consecutive frames a face must match the same student before attendance is recorded
MAX_MISSED_FRAMES = 10  # frames a face can be out of view before it is forgotten
MIN_IOU = 0.3  # boxes must overlap at least this much to be the same face


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
    """Gives each face a stable id across frames by matching boxes that overlap."""

    def __init__(self, max_missed: int = MAX_MISSED_FRAMES, min_iou: float = MIN_IOU):
        self.max_missed = max_missed
        self.min_iou = min_iou
        self._tracks: dict[int, _Track] = {}
        self._next_id = 1

    @property
    def ids(self) -> list[int]:
        return list(self._tracks)

    def track(self, track_id: int) -> _Track:
        return self._tracks[track_id]

    def update(self, boxes: list[Box]) -> list[int]:
        """Match this frame's face boxes to existing tracks. Returns one track id per box, in order."""
        unmatched = set(self._tracks)
        ids: list[int] = []
        for box in boxes:
            best_id, best = None, self.min_iou
            for track_id in unmatched:
                overlap = iou(self._tracks[track_id].box, box)
                if overlap >= best:
                    best_id, best = track_id, overlap
            if best_id is None:
                best_id = self._next_id
                self._next_id += 1
                self._tracks[best_id] = _Track(track_id=best_id, box=box)
            else:
                unmatched.discard(best_id)
                self._tracks[best_id].box = box
                self._tracks[best_id].missed = 0
            ids.append(best_id)

        for track_id in unmatched:
            track = self._tracks[track_id]
            track.missed += 1
            if track.missed > self.max_missed:
                del self._tracks[track_id]
        return ids


@dataclass(frozen=True)
class Decision:
    action: str  # "checking", "confirmed", "marked", "unknown", "not_live"
    student_no: str | None = None


class AttendanceDecider:
    """Decides, per tracked face, when a recognised student should be recorded as present."""

    def __init__(self, tracker: FaceTracker, confirm_frames: int = CONFIRM_FRAMES):
        self.tracker = tracker
        self.confirm_frames = confirm_frames

    def observe(self, track_id: int, *, is_live: bool | None, student_no: str | None) -> Decision:
        track = self.tracker.track(track_id)

        if track.marked:
            return Decision("marked", track.candidate)

        if is_live is False:
            self._reset(track, "not live")
            return Decision("not_live")

        if student_no is None:
            self._reset(track, "unknown")
            return Decision("unknown")

        if student_no == track.candidate:
            track.streak += 1
        else:
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
        track.candidate = None
        track.streak = 0
        track.label = label
