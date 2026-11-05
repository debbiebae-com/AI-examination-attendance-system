import threading
import time

import numpy as np

from app.vision.capture_flow import AcceptedFrame
from app.vision.embedder import EmbedResult
from app.vision.sample_worker import EmbedJob, SampleEmbedder, collect_samples


def emb(seed):
    v = np.random.default_rng(seed).normal(size=512).astype(np.float32)
    return v / np.linalg.norm(v)


def job(step, index, seed=1):
    return EmbedJob(step, index, np.zeros((4, 4, 3), dtype=np.uint8), (0, 0, 4, 4), None, 0.9)


def test_worker_embeds_every_submitted_frame():
    seen = []

    def embed_fn(image, bbox, kps):
        seen.append((bbox, kps))
        return EmbedResult(embedding=emb(len(seen)), is_live=True, live_score=0.9)

    worker = SampleEmbedder(embed_fn).start()
    worker.submit(job("straight", 0))
    worker.submit(job("left", 0))
    results = worker.finish()

    assert len(results) == 2
    assert all(r.embedding is not None and r.is_live for r in results)
    assert {(r.step, r.index) for r in results} == {("straight", 0), ("left", 0)}


def test_worker_records_errors_without_stopping():
    def embed_fn(image, bbox, kps):
        if bbox[0] == 1:
            raise RuntimeError("boom")
        return EmbedResult(embedding=emb(1), is_live=True, live_score=0.9)

    worker = SampleEmbedder(embed_fn).start()
    worker.submit(EmbedJob("straight", 0, np.zeros((4, 4, 3), np.uint8), (1, 0, 4, 4), None, 0.9))
    worker.submit(job("straight", 1))
    results = worker.finish()

    assert len(results) == 2
    failed = [r for r in results if r.error]
    assert len(failed) == 1 and "boom" in failed[0].error
    assert any(r.embedding is not None for r in results)


def test_finish_waits_for_in_flight_work():
    started = threading.Event()

    def slow_embed(image, bbox, kps):
        started.set()
        time.sleep(0.05)
        return EmbedResult(embedding=emb(1), is_live=True, live_score=0.9)

    worker = SampleEmbedder(slow_embed).start()
    worker.submit(job("straight", 0))
    assert started.wait(1.0)
    results = worker.finish(timeout=2.0)
    assert len(results) == 1 and results[0].embedding is not None
    assert worker.pending == 0


def test_collect_samples_joins_by_step_and_index():
    from app.vision.sample_worker import EmbeddedSample

    accepted = [AcceptedFrame("straight", 0, 0.9), AcceptedFrame("left", 0, 0.8)]
    results = [
        EmbeddedSample("left", 0, 0.8, embedding=emb(2), is_live=True),
        EmbeddedSample("straight", 0, 0.9, embedding=emb(1), is_live=True),
    ]
    samples, problems = collect_samples(accepted, results)
    assert not problems
    assert [s.step for s in samples] == ["straight", "left"]
    assert samples[0].det_score == 0.9


def test_collect_samples_reports_missing_and_failed():
    from app.vision.sample_worker import EmbeddedSample

    accepted = [AcceptedFrame("straight", 0, 0.9), AcceptedFrame("left", 0, 0.8), AcceptedFrame("right", 0, 0.8)]
    results = [
        EmbeddedSample("straight", 0, 0.9, embedding=emb(1)),
        EmbeddedSample("left", 0, 0.8, embedding=None, error="could not read"),
    ]
    samples, problems = collect_samples(accepted, results)
    assert len(samples) == 1
    assert len(problems) == 2
    assert any("could not read" in p for p in problems)
    assert any("right" in p for p in problems)
