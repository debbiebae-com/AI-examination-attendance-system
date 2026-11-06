"""Replay a consented video through the attendance recognizer, without writing attendance.

Run from backend: python -m app.vision.validate_video --video data/validation/entry.mp4
    --annotations data/validation/labels.json --output data/validation/report.json

Labels use zero-based frame numbers and original, unmirrored pixel boxes. Only labelled
frames are scored. All frames are processed for tracking/confirmation; this is NOT a
real-time camera benchmark (the live reader drops stale frames).
"""
import argparse
import json
import math
import platform
from pathlib import Path
from time import perf_counter

import numpy as np

from app.vision.attendance_flow import AttendanceDecider, FaceTracker
from app.vision.matcher import DEFAULT_MARGIN, DEFAULT_THRESHOLD


def read_labels(path):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("frames"), list) or not raw["frames"]:
        raise ValueError("Labels must contain a nonempty frames list")
    labels = {}
    for entry in raw["frames"]:
        if not isinstance(entry, dict):
            raise ValueError("Each frame entry must be an object")
        frame = entry.get("frame")
        if type(frame) is not int or frame < 0 or frame in labels:
            raise ValueError("Frame numbers must be unique nonnegative integers")
        faces = entry.get("faces")
        if not isinstance(faces, list):
            raise ValueError("Every labelled frame needs a faces list (empty is allowed)")
        for face in faces:
            if not isinstance(face, dict):
                raise ValueError("Each face entry must be an object")
            box = face.get("bbox")
            if (not isinstance(box, list) or len(box) != 4 or
                    any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in box) or
                    box[2] <= box[0] or box[3] <= box[1]):
                raise ValueError("Each bbox must be nonnegative [x1,y1,x2,y2] with positive area")
            if "student_no" not in face or (face["student_no"] is not None and
                    (not isinstance(face["student_no"], str) or not face["student_no"].strip())):
                raise ValueError("student_no must be an enrolled index or null for an unknown person")
        labels[frame] = faces
    return labels


def score_frame(truth, predictions, *, min_iou=0.5):
    """One-to-one spatial assignment first; never pair boxes based on predicted identity."""
    from scipy.optimize import linear_sum_assignment
    from app.vision.attendance_flow import iou

    counts = {key: 0 for key in (
        "known_face_observations", "known_correct", "known_wrong_identity", "known_not_identified",
        "unknown_face_observations", "unknown_false_accepts", "unknown_correct_rejects",
        "unknown_unresolved", "missed_face_detections", "unlabelled_detections",
    )}
    costs = np.ones((len(truth), len(predictions)), dtype=float)
    for i, expected in enumerate(truth):
        for j, actual in enumerate(predictions):
            overlap = iou(tuple(expected["bbox"]), tuple(actual["bbox"]))
            # Prioritize valid-match cardinality, then spatial overlap.
            costs[i, j] = (1 - overlap) / (max(len(truth), len(predictions)) + 1) if overlap >= min_iou else 2
    pairs = {}
    if truth and predictions:
        rows, cols = linear_sum_assignment(costs)
        pairs = {int(i): int(j) for i, j in zip(rows, cols) if costs[i, j] < 1}
    counts["unlabelled_detections"] = len(predictions) - len(pairs)
    for i, expected in enumerate(truth):
        known = expected["student_no"] is not None
        counts["known_face_observations" if known else "unknown_face_observations"] += 1
        actual = predictions[pairs[i]] if i in pairs else None
        if actual is None:
            counts["missed_face_detections"] += 1
        identity = actual["student_no"] if actual else None
        if known:
            result = "known_not_identified" if identity is None else (
                "known_correct" if identity == expected["student_no"] else "known_wrong_identity")
        else:
            result = "unknown_false_accepts" if identity else (
                "unknown_correct_rejects" if actual and actual["state"] == "unknown" else "unknown_unresolved")
        counts[result] += 1
    return counts


def replay(capture, embedder, matcher, labels, *, confirm=3):
    import cv2
    tracker = FaceTracker()
    decider = AttendanceDecider(tracker, confirm_frames=confirm)
    counts = {}
    latencies = []
    unique_marks = set()
    repeat_confirmations = 0
    frame_no = 0
    scored = 0
    peak_faces = 0
    started = perf_counter()
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        began = perf_counter()
        image = cv2.flip(frame, 1)  # Same orientation as the live attendance loop.
        faces = embedder.analyse(image)
        ids = tracker.update([tuple(f.bbox) for f in faces], [f.score for f in faces])
        peak_faces = max(peak_faces, len(faces))
        predictions = []
        for face, tid in zip(faces, ids):
            identity = None
            state = "untracked"
            if tid is not None:
                match = matcher.match(face.embedding).student_no if face.embedding is not None else None
                decision = decider.observe(tid, is_live=face.is_live, student_no=match)
                state = decision.action
                if face.embedding is None and state == "unknown":
                    state = "no_embedding"
                if state in ("confirmed", "marked"):
                    identity = decision.student_no
                if state == "confirmed":
                    if identity in unique_marks:
                        repeat_confirmations += 1
                    unique_marks.add(identity)
            predictions.append({"bbox": list(face.bbox), "student_no": identity, "state": state})
        latencies.append((perf_counter() - began) * 1000)
        if frame_no in labels:
            height, width = frame.shape[:2]
            truth = []
            for face in labels[frame_no]:
                x1, y1, x2, y2 = face["bbox"]
                if x2 > width or y2 > height:
                    raise ValueError(f"Annotation box exceeds video dimensions at frame {frame_no}")
                truth.append({"bbox": [width-x2, y1, width-x1, y2], "student_no": face["student_no"]})
            for key, value in score_frame(truth, predictions).items():
                counts[key] = counts.get(key, 0) + value
            scored += 1
        frame_no += 1
    if not frame_no:
        raise ValueError("Video contains no readable frames")
    if scored != len(labels):
        raise ValueError("Some labelled frames were never decoded; check frame numbers or video corruption")
    elapsed = perf_counter() - started
    known = counts["known_face_observations"]
    unknown = counts["unknown_face_observations"]
    return {
        "processed_frames": frame_no, "scored_frames": scored,
        "peak_detected_faces": peak_faces, "wall_seconds": elapsed,
        "replay_processed_fps": frame_no / elapsed,
        "mean_processing_ms": float(np.mean(latencies)),
        "p95_processing_ms": float(np.percentile(latencies, 95)),
        "counts": counts,
        "known_correct_rate": counts["known_correct"] / known if known else None,
        "unknown_false_accept_rate": counts["unknown_false_accepts"] / unknown if unknown else None,
        "simulated_unique_marks": len(unique_marks),
        "repeat_confirmations": repeat_confirmations,
        "attendance_database_writes": 0,
        "limitations": [
            "Rates are per labelled face observation, not independent people or entry events.",
            "Replay processes every decoded frame; the live camera drops frames, so replay cannot prove live throughput or accuracy.",
            "Untracked/checking/no-embedding faces are unresolved, not successful unknown rejections.",
            "Simulated marks test confirmation/deduplication only, not exam eligibility or database writes.",
            "Only supplied annotation frames are scored; annotate all visible faces in those frames.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default="buffalo_l")
    parser.add_argument("--det-size", type=int, default=480)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--confirm", type=int, default=3)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--margin", type=float, default=DEFAULT_MARGIN)
    args = parser.parse_args()
    if args.det_size < 32 or args.threads < 1 or args.confirm < 1:
        parser.error("det-size must be >=32; threads and confirm must be positive")
    if args.output.resolve() in (args.video.resolve(), args.annotations.resolve()):
        parser.error("Output must not overwrite the video or annotation file")
    if args.output.exists():
        parser.error("Output already exists; choose another report filename")
    try:
        labels = read_labels(args.annotations)
        import cv2
        from sqlalchemy import select
        from app.db import SessionLocal
        from app.models import FaceEmbedding, Student
        from app.vision.embedder import InsightFaceEmbedder
        from app.vision.gallery import load_matcher
        with SessionLocal() as session:
            enrolled = set(session.scalars(select(Student.student_no).join(FaceEmbedding)))
            expected = {f["student_no"] for faces in labels.values() for f in faces if f["student_no"]}
            missing = expected - enrolled
            if missing:
                raise ValueError(f"Labels contain identities without enrolled embeddings: {sorted(missing)}")
            matcher = load_matcher(session, threshold=args.threshold, margin=args.margin)
        if not len(matcher):
            raise ValueError("No enrolled embeddings; enroll/sync volunteers first")
        capture = cv2.VideoCapture(str(args.video))
        try:
            if not capture.isOpened():
                raise ValueError("Cannot open the video")
            embedder = InsightFaceEmbedder(model_name=args.model, det_size=(args.det_size, args.det_size),
                                           threads=args.threads, det_thresh=0.1, recognition_only=True)
            report = replay(capture, embedder, matcher, labels, confirm=args.confirm)
        finally:
            capture.release()
        report["settings"] = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}
        from importlib.metadata import version
        report["package_versions"] = {name: version(name) for name in ("insightface", "supervision", "onnxruntime")}
        report["execution_provider"] = "CPUExecutionProvider"
        report["hardware"] = {"platform": platform.platform(), "processor": platform.processor(), "python": platform.python_version()}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(report, output, indent=2)
        print(json.dumps(report, indent=2))
        print(f"Report saved to {args.output}. No attendance records were changed.")
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Validation failed: {exc}\n")


if __name__ == "__main__":
    main()
