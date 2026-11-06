import time

import numpy as np

from app.vision.camera import CameraReader, FpsMeter


class FakeCapture:
    """A stand-in for cv2.VideoCapture that yields numbered frames."""

    def __init__(self, count=None, delay=0.0):
        self.count = count
        self.delay = delay
        self.n = 0
        self.released = False

    def read(self):
        if self.delay:
            time.sleep(self.delay)
        if self.count is not None and self.n >= self.count:
            return False, None
        self.n += 1
        frame = np.full((4, 4, 3), self.n % 256, dtype=np.uint8)
        return True, frame

    def release(self):
        self.released = True


def _wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


def test_reader_delivers_the_latest_frame():
    capture = FakeCapture()
    reader = CameraReader(capture).start()
    try:
        assert _wait_for(lambda: reader.read()[0] > 0)
        first_seq, _ = reader.read()
        assert _wait_for(lambda: reader.read()[0] > first_seq)
        seq, frame = reader.read()
        assert frame is not None and seq > first_seq
    finally:
        reader.stop()
    assert capture.released


def test_reader_reports_when_camera_stops():
    capture = FakeCapture(count=3)
    reader = CameraReader(capture).start()
    try:
        assert _wait_for(lambda: reader.error is not None)
        assert "stopped sending frames" in reader.error
    finally:
        reader.stop()


def test_reader_sequence_numbers_are_monotonic():
    capture = FakeCapture(delay=0.001)
    reader = CameraReader(capture).start()
    try:
        assert _wait_for(lambda: reader.read()[0] >= 5)
        seen = []
        for _ in range(5):
            seen.append(reader.read()[0])
            time.sleep(0.003)
        assert seen == sorted(seen)
    finally:
        reader.stop()


def test_fps_meter_reports_a_positive_rate():
    meter = FpsMeter()
    now = 0.0
    for _ in range(10):
        now += 0.033  # ~30 fps
        meter.tick(now)
    assert 20.0 < meter.fps < 40.0
