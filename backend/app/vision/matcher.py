from dataclasses import dataclass

import numpy as np

# Cosine similarity thresholds for ArcFace-style embeddings.
# These are starting values. Tune them on real camera footage before the demo.
DEFAULT_THRESHOLD = 0.40  # best match must be at least this similar
DEFAULT_MARGIN = 0.05  # and must beat the second-best *different* student by this much


@dataclass(frozen=True)
class MatchResult:
    student_no: str | None  # None means no confident match
    score: float  # similarity to the best-matching enrolled student
    runner_up: float  # similarity to the best *different* enrolled student (-1 if none)

    @property
    def matched(self) -> bool:
        return self.student_no is not None


def _normalise(embedding: np.ndarray) -> np.ndarray:
    vector = np.asarray(embedding, dtype=np.float32).ravel()
    norm = float(np.linalg.norm(vector))
    if norm == 0.0:
        raise ValueError("Cannot match a zero-length embedding")
    return vector / norm


class FaceMatcher:
    """Matches a face embedding against enrolled students by cosine similarity.

    A student may have several enrollment photos. Each photo is kept, and a
    student's score is the best score across their photos.
    """

    def __init__(self, threshold: float = DEFAULT_THRESHOLD, margin: float = DEFAULT_MARGIN):
        self.threshold = threshold
        self.margin = margin
        self._student_nos: list[str] = []
        self._vectors: list[np.ndarray] = []

    def __len__(self) -> int:
        return len(self._student_nos)

    def enroll(self, student_no: str, embedding: np.ndarray) -> None:
        self._student_nos.append(student_no)
        self._vectors.append(_normalise(embedding))

    def match(self, embedding: np.ndarray) -> MatchResult:
        if not self._vectors:
            return MatchResult(student_no=None, score=0.0, runner_up=-1.0)

        query = _normalise(embedding)
        gallery = np.vstack(self._vectors)
        similarities = gallery @ query

        best_per_student: dict[str, float] = {}
        for student_no, similarity in zip(self._student_nos, similarities):
            score = float(similarity)
            if score > best_per_student.get(student_no, -np.inf):
                best_per_student[student_no] = score

        ranked = sorted(best_per_student.items(), key=lambda item: item[1], reverse=True)
        best_no, best_score = ranked[0]
        runner_up = ranked[1][1] if len(ranked) > 1 else -1.0

        confident = best_score >= self.threshold and (best_score - runner_up) >= self.margin
        return MatchResult(
            student_no=best_no if confident else None,
            score=best_score,
            runner_up=runner_up,
        )
