import numpy as np

from app.vision.matcher import FaceMatcher


def random_unit(seed: int, dim: int = 512) -> np.ndarray:
    v = np.random.default_rng(seed).normal(size=dim).astype(np.float32)
    return v / np.linalg.norm(v)


def test_enrolled_face_is_identified():
    matcher = FaceMatcher()
    for i, name in enumerate(["A", "B", "C"]):
        matcher.enroll(name, random_unit(i))

    noisy = random_unit(1) + 0.05 * random_unit(99)
    result = matcher.match(noisy)

    assert result.student_no == "B"
    assert result.matched
    assert result.score > 0.9


def test_unknown_face_is_refused():
    matcher = FaceMatcher()
    for i, name in enumerate(["A", "B", "C"]):
        matcher.enroll(name, random_unit(i))

    result = matcher.match(random_unit(12345))

    assert result.student_no is None
    assert not result.matched


def test_ambiguous_face_is_refused():
    # Two students who look almost identical to the matcher: refuse rather than guess.
    base = random_unit(7)
    matcher = FaceMatcher(threshold=0.4, margin=0.05)
    matcher.enroll("A", base)
    matcher.enroll("B", base + 0.01 * random_unit(8))

    result = matcher.match(base)

    assert result.student_no is None
    assert result.score - result.runner_up < 0.05


def test_several_photos_of_one_student_are_not_ambiguous():
    # Two photos of the same student must not count as a rival.
    base = random_unit(3)
    matcher = FaceMatcher()
    matcher.enroll("A", base)
    matcher.enroll("A", base + 0.05 * random_unit(4))
    matcher.enroll("B", random_unit(5))

    result = matcher.match(base)

    assert result.student_no == "A"
    assert result.runner_up < 0.4


def test_empty_gallery_matches_nobody():
    result = FaceMatcher().match(random_unit(1))
    assert result.student_no is None
    assert not result.matched
