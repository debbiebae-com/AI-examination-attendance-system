"""Embeds kept capture frames on a worker thread so the live preview never blocks.

The capture loop accepts a frame based on cheap pose signals, then hands the frame to
this worker, which runs the heavy ArcFace embedding and passive liveness check. Results
are joined back to the accepted frames by (step, index) when the capture finishes.

The worker takes any ``embed_fn(image, bbox, kps) -> EmbedResult`` so it is unit tested
without InsightFace.
"""

import queue
import threading
from dataclasses import dataclass

import numpy as np

from app.vision.capture_flow import AcceptedFrame, Sample
from app.vision.embedder import EmbedResult


@dataclass(frozen=True)
class EmbedJob:
    step: str
    index: int
    image: np.ndarray
    bbox: tuple[float, float, float, float]
    kps: np.ndarray | None
    det_score: float


@dataclass(frozen=True)
class EmbeddedSample:
    step: str
    index: int
    det_score: float
    embedding: np.ndarray | None = None
    is_live: bool | None = None
    live_score: float | None = None
    error: str | None = None


class SampleEmbedder:
    """A single background thread that embeds submitted frames in order."""

    def __init__(self, embed_fn):
        self._embed_fn = embed_fn
        self._queue: queue.Queue[EmbedJob | None] = queue.Queue()
        self._results: list[EmbeddedSample] = []
        self._lock = threading.Lock()
        self._in_flight = 0
        self._thread = threading.Thread(target=self._run, name="sample-embedder", daemon=True)

    def start(self) -> "SampleEmbedder":
        self._thread.start()
        return self

    def submit(self, job: EmbedJob) -> None:
        with self._lock:
            self._in_flight += 1
        self._queue.put(job)

    @property
    def pending(self) -> int:
        with self._lock:
            return self._in_flight

    def _run(self) -> None:
        while True:
            job = self._queue.get()
            if job is None:
                return
            try:
                result = self._embed_fn(job.image, job.bbox, job.kps)
                sample = EmbeddedSample(
                    step=job.step,
                    index=job.index,
                    det_score=job.det_score,
                    embedding=result.embedding,
                    is_live=result.is_live,
                    live_score=result.live_score,
                )
            except Exception as exc:  # keep going; the final check reports missing samples
                sample = EmbeddedSample(step=job.step, index=job.index, det_score=job.det_score, error=str(exc))
            with self._lock:
                self._results.append(sample)
                self._in_flight -= 1

    def finish(self, timeout: float = 60.0) -> list[EmbeddedSample]:
        """Stop accepting work, wait for queued jobs, and return every result."""
        self._queue.put(None)
        self._thread.join(timeout=timeout)
        with self._lock:
            return list(self._results)


def collect_samples(
    accepted: list[AcceptedFrame], results: list[EmbeddedSample]
) -> tuple[list[Sample], list[str]]:
    """Join accepted frames with their embedding results.

    Returns the usable samples and a list of human-readable problems (missing or
    failed embeddings), so the caller can refuse to save an incomplete capture.
    """
    by_key = {(result.step, result.index): result for result in results}
    samples: list[Sample] = []
    problems: list[str] = []
    for frame in accepted:
        result = by_key.get((frame.step, frame.index))
        if result is None:
            problems.append(f"{frame.step} sample {frame.index + 1} was not processed")
        elif result.embedding is None:
            detail = result.error or "the face could not be read"
            problems.append(f"{frame.step} sample {frame.index + 1}: {detail}")
        else:
            samples.append(Sample(frame.step, frame.index, result.embedding, frame.det_score))
    return samples, problems
