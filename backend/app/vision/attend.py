"""Live attendance: recognise enrolled students in the camera view and record them as present.

Run from backend/ on the PC with the webcam, after installing the vision extra:

    uv run --extra vision python -m app.vision.attend --exam CS101

Each face must match the same student for a few frames in a row before attendance is
recorded. Students who aren't registered for the exam (or fail eligibility) are shown, but
not recorded. Several faces can be recognised at once. Press q to stop.

The passive liveness model is OFF by default (it is unreliable on some cameras). Enable it
with --liveness. A background camera reader keeps the preview on the newest frame, and a live
FPS readout is shown.
"""

import argparse
from datetime import datetime
from time import perf_counter
from pathlib import Path

import cv2
from sqlalchemy import select

from app.attendance import NotEligible, mark_attendance
from app.db import SessionLocal, engine
from app.presentation import academic_display, camera_detail_lines
from app.live import LivePublisher
from app.models import Base, Exam, Student
from app.vision.attendance_flow import CONFIRM_FRAMES, AttendanceDecider, FaceTracker
from app.vision.camera import CameraReader, FpsMeter
from app.vision.embedder import DetectedFace, InsightFaceEmbedder
from app.vision.gallery import load_matcher
from app.vision.matcher import DEFAULT_MARGIN, DEFAULT_THRESHOLD

FONT = cv2.FONT_HERSHEY_SIMPLEX
WINDOW = "Live attendance (press q to stop)"
MAX_EVENTS_SHOWN = 3


def colour_for(label: str) -> tuple[int, int, int]:
    """BGR colour: green for recorded, yellow for still checking, red for refused."""
    if label.startswith("present") or label.startswith("already"):
        return (0, 200, 0)
    if label.startswith("checking"):
        return (0, 220, 255)
    return (0, 0, 255)


def record(
    *,
    exam_id: int,
    student_no: str,
    score: float,
    tid: int,
    decider: AttendanceDecider,
    names: dict[str, str],
    events: list[str],
    live: LivePublisher | None = None,
) -> None:
    name = names.get(student_no, student_no)
    stamp = datetime.now().strftime("%H:%M:%S")
    with SessionLocal() as session:
        try:
            _, created = mark_attendance(
                session,
                exam_id=exam_id,
                student_no=student_no,
                confidence=score,
                source="camera",
            )
        except NotEligible as exc:
            if live:
                live.event("not_eligible", track_id=tid, student_no=student_no, reasons=exc.reasons)
            decider.set_label(tid, "not eligible")
            events.append(f"{stamp} {name}: not eligible ({'; '.join(exc.reasons)})")
            return

    if live:
        live.event("present" if created else "already_present", track_id=tid, student_no=student_no, similarity=score)
    if created:
        decider.set_label(tid, "present")
        events.append(f"{stamp} {name} marked present")
    else:
        decider.set_label(tid, "already marked")
        events.append(f"{stamp} {name} was already marked")
    print(events[-1])


def wrap_overlay(text: str, max_width: int, scale: float = 0.43) -> list[str]:
    """Fit long indices/departments; split even a single long word if necessary."""
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if cv2.getTextSize(candidate, FONT, scale, 1)[0][0] <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        for char in word:
            if current and cv2.getTextSize(current + char, FONT, scale, 1)[0][0] > max_width:
                lines.append(current)
                current = ""
            current += char
    if current:
        lines.append(current)
    return lines


def draw_face_card(image, lines, x1, y1, y2, colour):
    height, width = image.shape[:2]
    if width < 32 or height < 32:
        return
    card_width = min(300, width - 8)
    wrapped = [part for line in lines for part in wrap_overlay(line, card_width - 16)]
    # Small camera frames cannot show unlimited text; leave all rendered lines inside the image.
    wrapped = wrapped[:max(1, (height - 16) // 18)]
    card_height = len(wrapped) * 18 + 12
    x = max(4, min(x1, width - card_width - 4))
    preferred_y = y1 - card_height - 4 if y1 >= card_height + 4 else y2 + 4
    y = max(4, min(preferred_y, height - card_height - 4))
    region = image[y:y + card_height, x:x + card_width]
    region[:] = (region.astype("float32") * 0.2).astype("uint8")
    cv2.rectangle(image, (x, y), (x + card_width, y + card_height), colour, 1)
    for index, text in enumerate(wrapped):
        cv2.putText(image, text, (x + 8, y + 18 + index * 18), FONT, 0.43,
                    colour if index == 0 else (235, 235, 235), 1, cv2.LINE_AA)


def draw(image, faces: list[DetectedFace], ids: list[int | None], tracker: FaceTracker, decider: AttendanceDecider, names: dict[str, str], events: list[str], fps: float = 0.0, academic: dict[str, dict] | None = None, exam_info: str = "") -> None:
    for face, tid in zip(faces, ids):
        if tid is None:
            continue
        track = tracker.track(tid)
        x1, y1, x2, y2 = (int(v) for v in face.bbox)
        who = names.get(track.candidate, track.candidate) if track.candidate else ""
        label = f"{who}: {track.label}" if who else track.label
        colour = colour_for(track.label)
        cv2.rectangle(image, (x1, y1), (x2, y2), colour, 2)
        lines = [label]
        # Academic data is only attached after identity confirmation, not while
        # the candidate is still being checked or the face is unknown.
        if track.marked and track.candidate:
            lines += camera_detail_lines(track.candidate, (academic or {}).get(track.candidate))
        draw_face_card(image, lines, x1, y1, y2, colour)

    height, width = image.shape[:2]
    for index, line in enumerate(wrap_overlay(exam_info, max(40, width - 145))[:2]):
        cv2.putText(image, line, (10, 22 + index * 18), FONT, 0.43, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(image, f"{fps:4.1f} fps", (width - 110, 30), FONT, 0.6, (200, 200, 200), 1, cv2.LINE_AA)
    for i, line in enumerate(events[-MAX_EVENTS_SHOWN:]):
        cv2.putText(image, line, (20, height - 20 - 26 * (MAX_EVENTS_SHOWN - 1 - i)), FONT, 0.55, (255, 255, 255), 2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stop-file", type=Path, help="local dashboard cooperative stop signal")
    parser.add_argument("--exam", required=True, help="course code, e.g. CS101")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--margin", type=float, default=DEFAULT_MARGIN)
    parser.add_argument("--confirm", type=int, default=CONFIRM_FRAMES, help="frames a match must hold")
    parser.add_argument("--det-size", type=int, default=640, help="detector resolution (lower = faster, may miss distant faces)")
    parser.add_argument("--det-threshold", type=float, default=0.1,
                        help="SCRFD confidence floor; retain low-score faces for ByteTrack")
    parser.add_argument("--track-threshold", type=float, default=0.5,
                        help="ByteTrack high-confidence association threshold")
    parser.add_argument("--track-buffer", type=int, default=10,
                        help="processed frames to retain a missing track")
    parser.add_argument("--threads", type=int, default=None, help="onnxruntime CPU threads")
    parser.add_argument(
        "--model",
        default="buffalo_l",
        help="InsightFace model pack; MUST match the one used for enrollment (ENROLL_MODEL on the web server)",
    )
    parser.add_argument(
        "--liveness",
        action="store_true",
        help="enable the passive liveness model (off by default; it is unreliable on some cameras)",
    )
    args = parser.parse_args()
    if not 0.1 <= args.det_threshold < args.track_threshold <= 0.9:
        parser.error("require 0.1 <= --det-threshold < --track-threshold <= 0.9")
    if args.confirm < 1 or args.track_buffer < 1:
        parser.error("--confirm and --track-buffer must be positive")

    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        exam = session.scalar(select(Exam).where(Exam.course_code == args.exam))
        if exam is None:
            raise SystemExit(f"No exam with course code {args.exam}")
        exam_id = exam.id
        exam_title = exam.course_title
        exam_info = f"{exam.course_code} | {exam.course_title} | {exam.hall}"
        matcher = load_matcher(session, threshold=args.threshold, margin=args.margin)
        students = session.scalars(select(Student)).all()
        names = {s.student_no: s.full_name for s in students}
        academic = {s.student_no: academic_display(s.student_no, s.programme, s.level) for s in students}

    if len(matcher) == 0:
        raise SystemExit("No enrolled faces found. Run the capture or photo enrollment first.")

    with LivePublisher(exam_id) as live:
        print(f"Exam {args.exam}: {exam_title}. {len(matcher)} face samples loaded.")
        print("Loading InsightFace...")
        if args.liveness:
            print("Passive liveness check: ON")
        else:
            print("Passive liveness check: OFF (recognition only)")
        embedder = InsightFaceEmbedder(
            model_name=args.model,
            liveness=args.liveness,
            det_size=(args.det_size, args.det_size),
            threads=args.threads,
            det_thresh=args.det_threshold,
            recognition_only=True,
        )

        tracker = FaceTracker(max_missed=args.track_buffer, activation_threshold=args.track_threshold)
        decider = AttendanceDecider(tracker, confirm_frames=args.confirm)
        camera = cv2.VideoCapture(args.camera)
        if not camera.isOpened():
            raise SystemExit(f"Cannot open camera {args.camera}. Try --camera 1.")
        try:
            camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

        reader = CameraReader(camera).start()
        fps_meter = FpsMeter()
        last_seq = -1
        events: list[str] = []
        try:
            while True:
                if args.stop_file and args.stop_file.exists():
                    break
                if reader.error:
                    raise SystemExit(reader.error)
                seq_id, frame = reader.read()
                if frame is None or seq_id == last_seq:
                    if cv2.waitKey(5) & 0xFF == ord("q"):
                        break
                    continue
                last_seq = seq_id
                image = cv2.flip(frame, 1)

                began = perf_counter()
                states = {}
                faces = embedder.analyse(image)
                ids = tracker.update([tuple(face.bbox) for face in faces], [face.score for face in faces])
                for face, tid in zip(faces, ids):
                    if tid is None:
                        continue
                    student_no, score = None, 0.0
                    if face.embedding is not None:
                        result = matcher.match(face.embedding)
                        student_no, score = result.student_no, result.score
                    decision = decider.observe(tid, is_live=face.is_live, student_no=student_no)
                    action = decision.action
                    if face.embedding is None and action == "unknown":
                        action = "no_embedding"
                    live.observe(tid, action, decision.student_no)
                    states[tid] = action
                    if decision.action == "confirmed":
                        record(
                            exam_id=exam_id,
                            student_no=decision.student_no,
                            score=score,
                            tid=tid,
                            decider=decider,
                            names=names,
                            events=events,
                            live=live,
                        )

                # Bound overlay history separately from the structured event ring.
                del events[:-MAX_EVENTS_SHOWN]
                live.frame(visible_faces=len(faces), states=states, fps=fps_meter.fps,
                           processing_ms=(perf_counter() - began) * 1000)
                draw(image, faces, ids, tracker, decider, names, events, fps_meter.fps, academic, exam_info)
                cv2.imshow(WINDOW, image)
                fps_meter.tick()
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
        finally:
            reader.stop()
            cv2.destroyAllWindows()

        print(f"Stopped. {len(live.identified)} distinct student(s) identified in this session.")


if __name__ == "__main__":
    main()
