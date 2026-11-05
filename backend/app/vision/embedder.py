"""InsightFace wrapper: SCRFD face detection, ArcFace embeddings, head pose and eye landmarks (buffalo_l).

Optionally runs InsightFace's liveness add-on, which rejects printed photos and screens.
Requires the optional `vision` extra. InsightFace is imported lazily, so the rest of the
backend and its tests run without it.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from app.vision.capture_flow import mean_eye_ratio


@dataclass(frozen=True)
class DetectedFace:
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2 in pixels
    score: float  # detection confidence
    embedding: np.ndarray | None = None  # L2-normalised 512-d; None if it could not be computed
    pose: tuple[float, float, float] | None = None  # pitch, yaw, roll in degrees
    eye_ratio: float | None = None  # mean eye aspect ratio; low values mean closed eyes
    is_live: bool | None = None  # None when the liveness check is not enabled
    landmarks: np.ndarray | None = None  # 68 x 2 points


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
        liveness: bool = False,
    ):
        import cv2
        from insightface.app import FaceAnalysis

        self._cv2 = cv2
        # buffalo_l = SCRFD detector + ArcFace recognition + 3D landmarks (pose). ctx_id=-1 runs on CPU.
        self._app = FaceAnalysis(
            name=model_name,
            providers=["CPUExecutionProvider"],
            addons=["liveness"] if liveness else None,
        )
        self._app.prepare(ctx_id=-1, det_size=det_size, det_thresh=det_thresh)

    def detect(self, image_path: Path) -> list[DetectedFace]:
        image = self._cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"Cannot read image {image_path}")
        return self.analyse(image)

    def analyse(self, image: np.ndarray) -> list[DetectedFace]:
        """Analyse a BGR image, as read by OpenCV."""
        return [_to_detected(face) for face in self._app.get(image)]


def _to_detected(face) -> DetectedFace:
    embedding = face.normed_embedding
    pose = face.get("pose")
    landmarks_3d = face.get("landmark_3d_68")
    landmarks = None if landmarks_3d is None else np.asarray(landmarks_3d, dtype=np.float32)[:, :2]
    liveness = face.get("liveness")
    return DetectedFace(
        bbox=tuple(float(x) for x in face.bbox),
        score=float(face.det_score),
        embedding=None if embedding is None else np.asarray(embedding, dtype=np.float32),
        pose=None if pose is None else tuple(float(x) for x in pose),
        eye_ratio=None if landmarks is None else mean_eye_ratio(landmarks),
        is_live=None if liveness is None else bool(getattr(liveness, "is_live", False)),
        landmarks=landmarks,
    )
