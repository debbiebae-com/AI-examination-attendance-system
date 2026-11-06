from pathlib import Path

import numpy as np

from app.vision.embedder import DetectedFace
from app.vision.evaluate import ensure_layout, run_evaluation


def unit(seed: int) -> np.ndarray:
    v = np.random.default_rng(seed).normal(size=512).astype(np.float32)
    return v / np.linalg.norm(v)


class FakeEmbedder:
    """Maps each photo's file name to the faces it contains."""

    def __init__(self, faces_by_name: dict[str, list[np.ndarray]]):
        self.faces_by_name = faces_by_name

    def detect(self, image_path: Path) -> list[DetectedFace]:
        if image_path.name not in self.faces_by_name:
            raise ValueError("unreadable")
        return [DetectedFace(bbox=(0, 0, 1, 1), score=0.9, embedding=e) for e in self.faces_by_name[image_path.name]]


def touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def build_probe_tree(root: Path) -> None:
    ensure_layout(root)
    touch(root / "reference" / "Ama.jpg")
    touch(root / "reference" / "Kwame.jpg")
    touch(root / "genuine" / "Ama" / "ama_2.jpg")
    touch(root / "genuine" / "Kwame" / "kwame_2.jpg")
    touch(root / "strangers" / "stranger_1.jpg")
    touch(root / "strangers" / "stranger_2.jpg")


def test_genuine_and_stranger_verdicts(tmp_path):
    build_probe_tree(tmp_path)
    ama, kwame = unit(1), unit(2)
    embedder = FakeEmbedder(
        {
            "Ama.jpg": [ama],
            "Kwame.jpg": [kwame],
            "ama_2.jpg": [ama + 0.05 * unit(90)],  # same person, slightly different photo
            "kwame_2.jpg": [kwame + 0.05 * unit(91)],
            "stranger_1.jpg": [unit(555)],  # unrelated face: should be refused
            "stranger_2.jpg": [ama],  # looks like Ama: should be a false accept
        }
    )

    report = run_evaluation(embedder, tmp_path, threshold=0.4)
    verdicts = {o.photo: o.verdict for o in report.outcomes}

    assert report.gallery_size == 2
    assert verdicts["ama_2.jpg"] == "correct"
    assert verdicts["kwame_2.jpg"] == "correct"
    assert verdicts["stranger_1.jpg"] == "correct_reject"
    assert verdicts["stranger_2.jpg"] == "false_accept"


def test_reference_and_probe_problems_are_reported(tmp_path):
    build_probe_tree(tmp_path)
    ama = unit(1)
    embedder = FakeEmbedder(
        {
            "Ama.jpg": [ama],
            "Kwame.jpg": [unit(2), unit(3)],  # two faces: not usable as a reference
            "ama_2.jpg": [],  # no face in this probe
            "kwame_2.jpg": [unit(2)],
            "stranger_1.jpg": [unit(555)],
            # stranger_2.jpg is missing from the mapping: unreadable
        }
    )

    report = run_evaluation(embedder, tmp_path, threshold=0.4)

    assert report.gallery_size == 1
    assert any("Kwame.jpg" in problem for problem in report.reference_problems)
    by_photo = {o.photo: o for o in report.outcomes}
    assert by_photo["ama_2.jpg"].verdict == "skipped"
    assert by_photo["stranger_2.jpg"].verdict == "skipped"


def test_sweep_shows_trade_off_between_thresholds(tmp_path):
    build_probe_tree(tmp_path)
    ama, kwame = unit(1), unit(2)
    embedder = FakeEmbedder(
        {
            "Ama.jpg": [ama],
            "Kwame.jpg": [kwame],
            "ama_2.jpg": [ama + 0.05 * unit(90)],
            "kwame_2.jpg": [kwame + 0.05 * unit(91)],
            "stranger_1.jpg": [unit(555)],
            "stranger_2.jpg": [unit(556)],
        }
    )

    report = run_evaluation(embedder, tmp_path, sweep=[0.2, 0.4, 0.9999])
    rows = {row.threshold: row for row in report.sweep}

    # A near-1.0 threshold rejects even the slightly altered genuine photos.
    assert rows[0.9999].genuine_correct == 0.0
    # A moderate threshold accepts the genuine people and refuses the strangers.
    assert rows[0.4].genuine_correct == 1.0
    assert rows[0.4].false_accepts == 0.0
