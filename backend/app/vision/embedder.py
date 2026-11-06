"""InsightFace wrapper: SCRFD detection, ArcFace embeddings, head pose and eye landmarks (buffalo_l).

Two tiers, so the live guidance loop stays smooth:

* ``guide(image)``  - detection + 68-point landmarks only. Cheap enough to run on every
  camera frame. No recognition and no liveness, which are the expensive parts.
* ``embed(image, bbox, kps)`` - ArcFace embedding + passive liveness for ONE already-detected
  face. Run only on the handful of frames the capture keeps, ideally on a worker thread.

``analyse(image)`` / ``detect(path)`` run the full pipeline and are used for photo enrollment
and live attendance.

Liveness uses InsightFace's add-on in "observe" mode: the embedding is always computed and
the liveness score is reported separately, so a single noisy liveness frame cannot block the
pipeline. Requires the optional `vision` extra; InsightFace is imported lazily.
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
    pose: tuple[float, float, float] | None = None  # pitch, yaw, roll in degrees (image space)
    eye_ratio: float | None = None  # mean eye aspect ratio; low values mean closed eyes
    is_live: bool | None = None  # None when the liveness check is not enabled
    live_score: float | None = None  # raw live probability 0..1
    landmarks: np.ndarray | None = None  # 68 x 2 points
    kps: np.ndarray | None = None  # 5 x 2 points (eyes, nose, mouth corners)


@dataclass(frozen=True)
class GuidedFace:
    """Cheap per-frame detection result used to drive the capture prompts."""

    bbox: tuple[float, float, float, float]
    score: float
    kps: np.ndarray | None = None
    pose: tuple[float, float, float] | None = None  # pitch, yaw, roll in degrees (image space)
    eye_ratio: float | None = None
    landmarks: np.ndarray | None = None


@dataclass(frozen=True)
class EmbedResult:
    """Heavy per-sample result: the face embedding and the passive liveness vote."""

    embedding: np.ndarray | None = None
    is_live: bool | None = None
    live_score: float | None = None


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
        threads: int | None = None,
        recognition_only: bool = False,
    ):
        import cv2
        import onnxruntime
        from insightface.app import FaceAnalysis

        self._cv2 = cv2
        sess_options = onnxruntime.SessionOptions()
        sess_options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        if threads is not None and threads > 0:
            sess_options.intra_op_num_threads = threads
            sess_options.inter_op_num_threads = 1
        # buffalo_l = SCRFD detector + ArcFace recognition + 3D landmarks (pose). ctx_id=-1 runs on CPU.
        # liveness_mode="observe" keeps embeddings flowing even when a frame's liveness vote is negative.
        self._app = FaceAnalysis(
            name=model_name,
            providers=["CPUExecutionProvider"],
            # Attendance needs SCRFD's five alignment points, not the additional
            # pose/68-point landmark or age/gender networks. Capture keeps them.
            allowed_modules=["detection", "recognition"] if recognition_only else None,
            addons=["liveness"] if liveness else None,
            liveness_mode="observe",
            sess_options=sess_options,
        )
        self._app.prepare(ctx_id=-1, det_size=det_size, det_thresh=det_thresh)

    # -- full pipeline (photo enrollment, live attendance) -----------------

    def detect(self, image_path: Path) -> list[DetectedFace]:
        image = self._cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"Cannot read image {image_path}")
        return self.analyse(image)

    def analyse(self, image: np.ndarray) -> list[DetectedFace]:
        """Analyse a BGR image, as read by OpenCV, running every enabled model."""
        return [_to_detected(face) for face in self._app.get(image)]

    # -- fast guidance tier (every camera frame) ---------------------------

    def guide(self, image: np.ndarray) -> list[GuidedFace]:
        """Detect faces and read pose + eyes, skipping recognition and liveness."""
        from insightface.app.common import Face

        bboxes, kpss = self._app.det_model.detect(image)
        landmark_model = self._app.models.get("landmark_3d_68")
        faces: list[GuidedFace] = []
        for i in range(bboxes.shape[0]):
            kps = None if kpss is None else np.asarray(kpss[i], dtype=np.float32)
            face = Face(bbox=bboxes[i, 0:4], kps=kps, det_score=float(bboxes[i, 4]))
            if landmark_model is not None:
                landmark_model.get(image, face)
            landmarks_3d = face.get("landmark_3d_68")
            landmarks = None if landmarks_3d is None else np.asarray(landmarks_3d, dtype=np.float32)[:, :2]
            pose = face.get("pose")
            faces.append(
                GuidedFace(
                    bbox=tuple(float(x) for x in face.bbox),
                    score=float(face.det_score),
                    kps=kps,
                    pose=None if pose is None else tuple(float(x) for x in pose),
                    eye_ratio=None if landmarks is None else mean_eye_ratio(landmarks),
                    landmarks=landmarks,
                )
            )
        return faces

    # -- heavy sample tier (kept frames only) ------------------------------

    def embed(self, image: np.ndarray, bbox, kps) -> EmbedResult:
        """Compute the embedding and passive liveness for one already-detected face."""
        from insightface.app.common import Face

        if kps is None:
            return EmbedResult()
        face = Face(bbox=np.asarray(bbox, dtype=np.float32), kps=np.asarray(kps, dtype=np.float32), det_score=1.0)
        liveness = self._app.addons.get("liveness")
        if liveness is not None:
            liveness.get(image, face)
        recognition = self._app.models.get("recognition")
        if recognition is not None:
            recognition.get(image, face)
        embedding = face.normed_embedding
        liveness_info = face.get("liveness") or {}
        return EmbedResult(
            embedding=None if embedding is None else np.asarray(embedding, dtype=np.float32),
            is_live=liveness_info.get("is_live"),
            live_score=liveness_info.get("live_score"),
        )


def _to_detected(face) -> DetectedFace:
    embedding = face.normed_embedding
    pose = face.get("pose")
    landmarks_3d = face.get("landmark_3d_68")
    landmarks = None if landmarks_3d is None else np.asarray(landmarks_3d, dtype=np.float32)[:, :2]
    liveness = face.get("liveness") or {}
    kps = face.get("kps")
    return DetectedFace(
        bbox=tuple(float(x) for x in face.bbox),
        score=float(face.det_score),
        embedding=None if embedding is None else np.asarray(embedding, dtype=np.float32),
        pose=None if pose is None else tuple(float(x) for x in pose),
        eye_ratio=None if landmarks is None else mean_eye_ratio(landmarks),
        is_live=liveness.get("is_live"),
        live_score=liveness.get("live_score"),
        landmarks=landmarks,
        kps=None if kps is None else np.asarray(kps, dtype=np.float32),
    )
