"""Threaded camera reader and an FPS meter, so the preview never stalls on inference.

OpenCV's VideoCapture buffers frames internally. When processing is slower than the
camera, a naive read-process loop falls further and further behind, which feels like a
very low frame rate even when the camera is fine. This reader grabs frames on its own
thread and always hands back the LATEST one, dropping stale frames.

The reader takes any object with ``read()`` and ``release()`` (a cv2.VideoCapture in
production, a fake in tests), so it is unit tested without a camera.
"""

import threading
import time
from collections import deque


class CameraReader:
    """Reads frames on a background thread; consumers poll for the newest frame."""

    def __init__(self, capture):
        self._capture = capture
        self._lock = threading.Lock()
        self._frame = None
        self._seq = 0
        self._error: str | None = None
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._run, name="camera-reader", daemon=True)

    def start(self) -> "CameraReader":
        self._thread.start()
        return self

    def _run(self) -> None:
        while not self._stopped.is_set():
            ok, frame = self._capture.read()
            if not ok or frame is None:
                with self._lock:
                    self._error = "The camera stopped sending frames."
                return
            with self._lock:
                self._frame = frame
                self._seq += 1

    def read(self):
        """Return (sequence_number, frame). The sequence number lets callers skip frames
        they have already processed. frame is None until the first frame arrives."""
        with self._lock:
            return self._seq, self._frame

    @property
    def error(self) -> str | None:
        with self._lock:
            return self._error

    def stop(self) -> None:
        self._stopped.set()
        self._thread.join(timeout=2.0)
        try:
            self._capture.release()
        except Exception:
            pass


class FpsMeter:
    """Exponential moving average of the processing frame rate."""

    def __init__(self, alpha: float = 0.1, window: int = 30):
        self._alpha = alpha
        self._stamps: deque[float] = deque(maxlen=window)
        self._fps: float | None = None

    def tick(self, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        self._stamps.append(now)
        if len(self._stamps) >= 2:
            instant = (len(self._stamps) - 1) / (self._stamps[-1] - self._stamps[0])
            self._fps = instant if self._fps is None else self._alpha * instant + (1 - self._alpha) * self._fps
        return self._fps or 0.0

    @property
    def fps(self) -> float:
        return self._fps or 0.0
