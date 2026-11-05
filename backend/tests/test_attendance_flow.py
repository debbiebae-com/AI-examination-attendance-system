import pytest

from app.vision.attendance_flow import AttendanceDecider, FaceTracker, iou


def box(x: float, y: float, size: float = 100) -> tuple[float, float, float, float]:
    return (x, y, x + size, y + size)


def test_iou_identical_and_disjoint_boxes():
    assert iou(box(0, 0), box(0, 0)) == pytest.approx(1.0)
    assert iou(box(0, 0), box(500, 500)) == 0.0


def test_tracker_keeps_same_id_for_a_moving_face():
    tracker = FaceTracker()
    first = tracker.update([box(100, 100)])[0]
    second = tracker.update([box(108, 103)])[0]
    assert first == second


def test_tracker_gives_new_id_to_a_different_face():
    tracker = FaceTracker()
    left_id = tracker.update([box(0, 0)])[0]
    ids = tracker.update([box(0, 0), box(400, 0)])
    assert ids[0] == left_id
    assert ids[1] != left_id


def test_two_faces_in_one_frame_keep_separate_ids():
    tracker = FaceTracker()
    first = tracker.update([box(0, 0), box(400, 0)])
    second = tracker.update([box(4, 0), box(404, 0)])
    assert first == second
    assert first[0] != first[1]


def test_track_is_forgotten_after_too_many_missed_frames():
    tracker = FaceTracker(max_missed=2)
    track_id = tracker.update([box(0, 0)])[0]
    tracker.update([])
    tracker.update([])
    assert track_id in tracker.ids
    tracker.update([])
    assert track_id not in tracker.ids


def test_confirms_after_consecutive_matches_of_same_student():
    tracker = FaceTracker()
    decider = AttendanceDecider(tracker, confirm_frames=3)
    track_id = tracker.update([box(0, 0)])[0]

    assert decider.observe(track_id, is_live=True, student_no="UGS-26-001").action == "checking"
    assert decider.observe(track_id, is_live=True, student_no="UGS-26-001").action == "checking"
    decision = decider.observe(track_id, is_live=True, student_no="UGS-26-001")

    assert decision.action == "confirmed"
    assert decision.student_no == "UGS-26-001"


def test_attendance_is_only_recorded_once_per_face():
    tracker = FaceTracker()
    decider = AttendanceDecider(tracker, confirm_frames=2)
    track_id = tracker.update([box(0, 0)])[0]
    for _ in range(2):
        decider.observe(track_id, is_live=True, student_no="UGS-26-001")
    assert decider.observe(track_id, is_live=True, student_no="UGS-26-001").action == "marked"


def test_switching_student_restarts_the_count():
    tracker = FaceTracker()
    decider = AttendanceDecider(tracker, confirm_frames=3)
    track_id = tracker.update([box(0, 0)])[0]
    decider.observe(track_id, is_live=True, student_no="A")
    decider.observe(track_id, is_live=True, student_no="A")
    assert decider.observe(track_id, is_live=True, student_no="B").action == "checking"
    assert tracker.track(track_id).streak == 1


def test_unknown_face_resets_the_count():
    tracker = FaceTracker()
    decider = AttendanceDecider(tracker, confirm_frames=3)
    track_id = tracker.update([box(0, 0)])[0]
    decider.observe(track_id, is_live=True, student_no="A")
    decider.observe(track_id, is_live=True, student_no="A")
    assert decider.observe(track_id, is_live=True, student_no=None).action == "unknown"
    assert decider.observe(track_id, is_live=True, student_no="A").action == "checking"


def test_photo_or_screen_never_confirms():
    tracker = FaceTracker()
    decider = AttendanceDecider(tracker, confirm_frames=1)
    track_id = tracker.update([box(0, 0)])[0]
    for _ in range(5):
        assert decider.observe(track_id, is_live=False, student_no="A").action == "not_live"
    assert not tracker.track(track_id).marked


def test_checking_label_shows_progress():
    tracker = FaceTracker()
    decider = AttendanceDecider(tracker, confirm_frames=3)
    track_id = tracker.update([box(0, 0)])[0]
    decider.observe(track_id, is_live=True, student_no="A")
    assert tracker.track(track_id).label == "checking 1/3"


def test_several_faces_are_decided_independently():
    tracker = FaceTracker()
    decider = AttendanceDecider(tracker, confirm_frames=2)
    left, right = tracker.update([box(0, 0), box(400, 0)])
    decider.observe(left, is_live=True, student_no="A")
    decider.observe(right, is_live=True, student_no="B")
    assert decider.observe(left, is_live=True, student_no="A").action == "confirmed"
    assert decider.observe(right, is_live=True, student_no="B").action == "confirmed"
