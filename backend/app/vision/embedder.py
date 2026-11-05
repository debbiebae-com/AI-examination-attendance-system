"""InsightFace wrapper: SCRFD face detection plus ArcFace embeddings (buffalo_l).

Requires the optional `vision` extra. InsightFace is imported lazily, so the
rest of the backend and its tests run without it.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class DetectedFace:
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2 in pixels
    score: float  # detection confidence
    embedding: np.ndarray  # L2-normalised 512-d ArcFace embedding


class FaceEmbedder(Protocol):
    def detect(self, image_path: Path) -> list[DetectedFace]:
        """Return every face in the image. Raise ValueError if the image cannot be read."""
        ...


class InsightFaceEmbedder:
    def __init__(
        self,
        model_name: str = "buffalo_l",
        det_size: tuple[int, int] = (640, 640),
        det_thresh: float = 0.5,
    ):
        import cv2
        from insightface.app import FaceAnalysis

        self._cv2 = cv2
        # buffalo_l = SCRFD detector + ArcFace recognition. ctx_id=-1 runs on CPU.
        self._app = FaceAnalysis(name=model_name, providers=["CPUExecutionProvider"])
        self._app.prepare(ctx_id=-1, det_size=det_size, det_thresh=det_thresh)

    def detect(self, image_path: Path) -> list[DetectedFace]:
        image = self._cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"Cannot read image {image_path}")
        faces = self._app.get(image)
        results: list[DetectedFace] = []
        for face in faces:
            if face.normed_embedding is None:  # detected, but no embedding could be computed
                continue
            results.append(
                DetectedFace(
                    bbox=tuple(float(x) for x in face.bbox),
                    score=float(face.det_score),
                    embedding=np.asarray(face.normed_embedding, dtype=np.float32),
                )
            )
        return results
