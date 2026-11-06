"""One-time model/dependency warmup for Prepare Demo.cmd. Never opens a camera or DB."""
from app.config import ENROLL_MODEL


def prepare_models():
    # Enrollment needs the full pack (including pose landmarks), not just recognition.
    # All optional imports remain here so the ordinary API stays lightweight.
    import supervision  # noqa: F401
    from app.vision.embedder import InsightFaceEmbedder

    InsightFaceEmbedder(model_name=ENROLL_MODEL, det_size=(480, 480), threads=4)
    print("Recognition and local enrollment models are ready. No camera or student data was accessed.", flush=True)


if __name__ == "__main__":
    prepare_models()
