"""Face recognition spike: check InsightFace buffalo_l on the synthetic demo photos.

Run from backend/ after installing the vision extra:
    uv sync --extra vision
    uv run python -m app.vision.spike

The first run downloads the buffalo_l model to ~/.insightface.
"""

import argparse

import numpy as np
from sqlalchemy import select

from app.db import SessionLocal, engine
from app.models import Base, FaceEmbedding, Student
from app.vision.embedder import InsightFaceEmbedder
from app.vision.gallery import enroll_students, load_matcher
from app.vision.matcher import DEFAULT_MARGIN, DEFAULT_THRESHOLD


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--margin", type=float, default=DEFAULT_MARGIN)
    args = parser.parse_args()

    Base.metadata.create_all(engine)
    print("Loading InsightFace buffalo_l (the first run downloads the model)...")
    embedder = InsightFaceEmbedder()

    print("\n== 1. Enrollment: one face per photo expected ==")
    with SessionLocal() as session:
        for result in enroll_students(session, embedder):
            detail = f"det_score={result.det_score:.2f}" if result.det_score is not None else f"faces={result.faces_found}"
            print(f"{result.student_no}  {result.status:<15} {detail:<16} {result.photo}")

    print("\n== 2. Self-match: each enrolled photo should match its own student ==")
    with SessionLocal() as session:
        matcher = load_matcher(session, threshold=args.threshold, margin=args.margin)
        rows = session.execute(
            select(Student.student_no, FaceEmbedding.source_photo, FaceEmbedding.embedding)
            .join(FaceEmbedding, FaceEmbedding.student_id == Student.id)
            .order_by(Student.student_no)
        ).all()

    passed = 0
    for student_no, photo, blob in rows:
        result = matcher.match(np.frombuffer(blob, dtype=np.float32))
        ok = result.student_no == student_no
        passed += ok
        print(
            f"{'PASS' if ok else 'FAIL'}  {student_no} -> {result.student_no or 'no match':<12} "
            f"score={result.score:.3f}  runner_up={result.runner_up:.3f}  {photo}"
        )
    print(f"\n{passed}/{len(rows)} enrolled photos matched their own student.")


if __name__ == "__main__":
    main()
