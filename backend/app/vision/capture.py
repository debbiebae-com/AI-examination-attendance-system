"""Guided face capture for one person: look straight, turn left, turn right.

Runs in a window on the PC with the webcam. Each accepted frame is stored as a face
embedding for the student, replacing any earlier capture for that student.

Designed for a smooth, low-retry experience:

* The preview is mirrored (selfie-style) and head angles are converted to PERSON space,
  so "turn to your LEFT" always means the person's own left. On-screen arrows point the
  right way, and turning the wrong way gets an explicit correction.
* Every camera frame runs only the cheap detector + landmarks. The heavy embedding and
  liveness check run on a worker thread for the few kept frames, so the preview stays fast.
* A background camera reader always shows the newest frame (no stale-frame lag), and an
  FPS readout is shown live.
* Liveness comes from the turn challenge (a photo or screen cannot turn its head). The
  passive liveness model is OPTIONAL and OFF by default because it is unreliable on some
  cameras; enable it with --liveness, in which case its vote is aggregated over the whole
  capture instead of rejecting single frames. There is no blink step.

Run from backend/ after installing the vision extra:

    uv run --extra vision python -m app.vision.capture --student-no VOL-001 --name "Ama Mensah"

Options:
    --exam CODE       also register the student for this exam (e.g. CS101)
    --camera 1        use if the wrong camera opens
    --no-mirror       for camera feeds that are already mirrored (e.g. some phone apps)
    --det-size 320    guidance detector resolution (lower = faster)
    --threads N       onnxruntime CPU threads
    --liveness        enable the passive liveness model (off by default)

Press q or Esc in the window to cancel. Press m to flip the mirror if left/right feels
inverted (useful when a phone-as-webcam app already mirrors its feed).
"""

import argparse
import time
from pathlib import Path

import cv2
from sqlalchemy import select

from app.db import SessionLocal, engine
from app.models import Base, Exam, Registration, Student
from app.vision.camera import CameraReader, FpsMeter
from app.vision.camera_source import open_camera
from app.vision.capture_flow import (
    PROMPTS,
    STEPS,
    STRAIGHT_MAX_DEG,
    TURN_MIN_DEG,
    CaptureSequence,
    FrameSignal,
    capture_save_verdict,
    missing_steps,
)
from app.vision.embedder import GuidedFace, InsightFaceEmbedder
from app.vision.gallery import save_capture_samples
from app.vision.sample_worker import EmbedJob, SampleEmbedder, collect_samples

FONT = cv2.FONT_HERSHEY_SIMPLEX
WINDOW = "Face capture (q or Esc to cancel)"

WHITE = (245, 245, 245)
GREEN = (90, 200, 90)
AMBER = (0, 190, 255)
RED = (80, 80, 235)
DIM = (170, 170, 170)
PANEL = (30, 30, 30)


def get_or_create_student(session, student_no: str, name: str | None, exam_code: str | None, *, commit=True) -> Student:
    student = session.scalar(select(Student).where(Student.student_no == student_no))
    if student is None:
        if not name:
            raise SystemExit(f"{student_no} is not in the database. Pass --name to create it.")
        student = Student(
            student_no=student_no,
            full_name=name,
            programme="Volunteer (test)",
            level=100,
            fees_cleared=True,
            suspended=False,
        )
        session.add(student)
        session.flush()

    if exam_code:
        exam = session.scalar(select(Exam).where(Exam.course_code == exam_code))
        if exam is None:
            raise SystemExit(f"No exam with course code {exam_code}")
        already = session.scalar(
            select(Registration.id).where(Registration.student_id == student.id, Registration.exam_id == exam.id)
        )
        if already is None:
            session.add(Registration(student_id=student.id, exam_id=exam.id))

    if commit:
        session.commit()
    return student


def to_signal(faces: list[GuidedFace], image_shape, *, mirrored: bool) -> FrameSignal:
    """Convert a detection into a person-space signal.

    InsightFace reports yaw in image space: for an UNMIRRORED image, positive yaw means
    the person turned towards their own left (verified against the model's pose code).
    A mirrored preview flips that sign, so we negate it here. The result is always
    positive when the person turns towards their OWN left, regardless of the camera.
    """
    if len(faces) != 1:
        return FrameSignal(face_count=len(faces))
    face = faces[0]
    height, width = image_shape[:2]
    x1, y1, x2, y2 = face.bbox
    yaw = None
    if face.pose is not None:
        image_yaw = face.pose[1]
        yaw = -image_yaw if mirrored else image_yaw
    return FrameSignal(
        face_count=1,
        det_score=face.score,
        yaw=yaw,
        eye_ratio=face.eye_ratio,
        face_cx=((x1 + x2) / 2.0) / width,
        face_cy=((y1 + y2) / 2.0) / height,
        face_w=(x2 - x1) / width,
    )


# -- overlay ---------------------------------------------------------------


def _panel(image, x1, y1, x2, y2, alpha: float = 0.55) -> None:
    region = image[y1:y2, x1:x2]
    overlay = region.copy()
    overlay[:] = PANEL
    cv2.addWeighted(overlay, alpha, region, 1 - alpha, 0, region)


def _text_center(image, text, y, scale=0.8, color=WHITE, thickness=2):
    (tw, _), _ = cv2.getTextSize(text, FONT, scale, thickness)
    x = max(8, (image.shape[1] - tw) // 2)
    cv2.putText(image, text, (x, y), FONT, scale, color, thickness, cv2.LINE_AA)


def _draw_arrow(image, direction, y, label):
    """direction: -1 points to screen-left, +1 to screen-right."""
    w = image.shape[1]
    length = int(w * 0.16)
    margin = int(w * 0.05)
    if direction < 0:
        start, end = (margin + length, y), (margin, y)
        text_x = margin
    else:
        start, end = (w - margin - length, y), (w - margin, y)
        text_x = w - margin - length
    cv2.arrowedLine(image, start, end, AMBER, 6, cv2.LINE_AA, tipLength=0.35)
    cv2.putText(image, label, (text_x, y - 16), FONT, 0.7, AMBER, 2, cv2.LINE_AA)


def _draw_chips(image, sequence):
    x = 14
    y = 14
    chip_w = 150
    for step in STEPS:
        got, need = sequence.progress(step)
        current = sequence.current_step == step
        done = got >= need
        color = GREEN if done else (AMBER if current else DIM)
        cv2.rectangle(image, (x, y), (x + chip_w, y + 40), (50, 50, 50), -1)
        cv2.rectangle(image, (x, y), (x + chip_w, y + 40), color, 2 if current else 1)
        label = f"{step} {got}/{need}"
        cv2.putText(image, label, (x + 10, y + 26), FONT, 0.55, color, 1, cv2.LINE_AA)
        if done:
            cv2.line(image, (x + chip_w - 26, y + 20), (x + chip_w - 19, y + 28), GREEN, 2, cv2.LINE_AA)
            cv2.line(image, (x + chip_w - 19, y + 28), (x + chip_w - 8, y + 12), GREEN, 2, cv2.LINE_AA)
        x += chip_w + 10


def _draw_yaw_gauge(image, sequence, signal, mirrored):
    h, w = image.shape[:2]
    bar_w = int(w * 0.6)
    x1 = (w - bar_w) // 2
    x2 = x1 + bar_w
    y = h - 46
    cv2.rectangle(image, (x1, y), (x2, y + 12), (60, 60, 60), -1)
    center = (x1 + x2) // 2
    scale = (bar_w / 2) / 45.0  # +-45 degrees across the bar

    # Screen direction that corresponds to the person's own left.
    left_dir = -1 if mirrored else 1
    step = sequence.current_step
    if step == "straight":
        half = int(STRAIGHT_MAX_DEG * scale)
        cv2.rectangle(image, (center - half, y), (center + half, y + 12), (60, 110, 60), -1)
    elif step in ("left", "right"):
        sign = left_dir if step == "left" else -left_dir
        a = center + int(sign * TURN_MIN_DEG * scale)
        b = center + int(sign * 45 * scale)
        cv2.rectangle(image, (min(a, b), y), (max(a, b), y + 12), (60, 110, 60), -1)

    yaw = sequence.smoothed_yaw
    if yaw is not None:
        marker = center + int(left_dir * max(-45.0, min(45.0, yaw)) * scale)
        cv2.circle(image, (marker, y + 6), 8, WHITE, -1, cv2.LINE_AA)
    cv2.putText(image, "L", (x1 - 22 if left_dir < 0 else x2 + 8, y + 11), FONT, 0.5, DIM, 1, cv2.LINE_AA)
    cv2.putText(image, "R", (x2 + 8 if left_dir < 0 else x1 - 22, y + 11), FONT, 0.5, DIM, 1, cv2.LINE_AA)


def draw_overlay(image, faces, sequence, message, signal, fps, mirrored, flash):
    h, w = image.shape[:2]
    box_color = GREEN if len(faces) == 1 else RED
    for face in faces:
        x1, y1, x2, y2 = (int(v) for v in face.bbox)
        cv2.rectangle(image, (x1, y1), (x2, y2), box_color, 2)

    _panel(image, 0, 0, w, 64)
    _draw_chips(image, sequence)
    cv2.putText(image, f"{fps:4.1f} fps", (w - 110, 34), FONT, 0.6, DIM, 1, cv2.LINE_AA)

    step = sequence.current_step
    _panel(image, 0, 64, w, 128)
    _text_center(image, PROMPTS[step] if step else "Capture complete", 92, 0.85, WHITE)
    if message:
        _text_center(image, message, 118, 0.6, AMBER, 1)

    if step in ("left", "right"):
        left_dir = -1 if mirrored else 1
        direction = left_dir if step == "left" else -left_dir
        label = "YOUR LEFT" if step == "left" else "YOUR RIGHT"
        _draw_arrow(image, direction, h // 2, label)

    mirror_hint = "mirror: on" if mirrored else "mirror: off"
    cv2.putText(image, f"{mirror_hint}  (m to flip)", (16, h - 16), FONT, 0.5, DIM, 1, cv2.LINE_AA)
    _draw_yaw_gauge(image, sequence, signal, mirrored)

    if flash and time.monotonic() < flash:
        _text_center(image, "Sample saved", h - 80, 0.7, GREEN)


# -- main loop -------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--student-no", required=True)
    parser.add_argument("--name", help="full name, used only when creating a new student")
    parser.add_argument("--exam", help="course code to register the student for")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--samples", type=int, default=3, help="frames to keep per turn or straight step")
    parser.add_argument("--no-mirror", action="store_true", help="use if the camera feed is already mirrored")
    parser.add_argument("--det-size", type=int, default=320, help="guidance detector resolution (lower = faster)")
    parser.add_argument("--threads", type=int, default=None, help="onnxruntime CPU threads")
    parser.add_argument(
        "--liveness",
        action="store_true",
        help="enable the passive liveness model (off by default; the turn challenge is always active)",
    )
    parser.add_argument("--camera-source", choices=["pc", "droidcam"], default="pc")
    parser.add_argument("--capture-backend", choices=["auto", "dshow", "msmf"], default="auto")
    parser.add_argument("--model", default="buffalo_l")
    parser.add_argument("--stop-file", type=Path)
    args = parser.parse_args()

    mirrored = not args.no_mirror
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        student = session.scalar(select(Student).where(Student.student_no == args.student_no))
        if student is None and not args.name:
            raise SystemExit("Provide a full name for a new volunteer")
        full_name = student.full_name if student else args.name

    print("Loading InsightFace (the first run downloads the models)...")
    if args.liveness:
        print("Passive liveness check: ON")
    else:
        print("Passive liveness check: OFF (the left/right turn challenge still proves liveness)")
    embedder = InsightFaceEmbedder(
        model_name=args.model, liveness=args.liveness, det_size=(args.det_size, args.det_size), threads=args.threads
    )

    if args.stop_file and args.stop_file.exists():
        print("Cancelled. Nothing was saved.")
        return
    camera = open_camera(args.camera, args.capture_backend, args.camera_source == "droidcam")
    try:
        camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass

    reader = CameraReader(camera).start()
    worker = SampleEmbedder(embedder.embed).start()
    sequence = CaptureSequence(samples_per_step=args.samples)
    fps_meter = FpsMeter()
    flash_until = 0.0
    last_seq = -1
    cancelled = False
    last_display = None

    try:
        while not sequence.done:
            if args.stop_file and args.stop_file.exists():
                cancelled = True
                break
            if reader.error:
                raise SystemExit(reader.error)
            seq_id, frame = reader.read()
            if frame is None or seq_id == last_seq:
                key = cv2.waitKey(5) & 0xFF
                if key in (ord("q"), 27):
                    cancelled = True
                    break
                if key == ord("m"):
                    mirrored = not mirrored
                continue
            last_seq = seq_id

            display = cv2.flip(frame, 1) if mirrored else frame
            faces = embedder.guide(display)
            signal = to_signal(faces, display.shape, mirrored=mirrored)
            verdict = sequence.process(signal)
            if verdict.accepted is not None and faces:
                face = faces[0]
                accepted = sequence.accepted_frames[-1]
                worker.submit(
                    EmbedJob(accepted.step, accepted.index, display.copy(), face.bbox, face.kps, face.score)
                )
                flash_until = time.monotonic() + 0.6

            last_display = display
            draw_overlay(display, faces, sequence, verdict.message, signal, fps_meter.fps, mirrored, flash_until)
            cv2.imshow(WINDOW, display)
            fps_meter.tick()
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                cancelled = True
                break
            if key == ord("m"):
                mirrored = not mirrored

        # Drain the embedding worker while keeping the window responsive.
        if not cancelled:
            while worker.pending > 0:
                if args.stop_file and args.stop_file.exists():
                    cancelled = True
                    break
                if last_display is not None:
                    finishing = last_display.copy()
                    _panel(finishing, 0, 0, finishing.shape[1], finishing.shape[0], 0.5)
                    _text_center(finishing, "Finishing... checking samples", finishing.shape[0] // 2, 0.9)
                    cv2.imshow(WINDOW, finishing)
                if cv2.waitKey(10) & 0xFF in (ord("q"), 27):
                    cancelled = True
                    break
    finally:
        reader.stop()
        results = worker.finish()
        cv2.destroyAllWindows()

    if cancelled or not sequence.done:
        print("Cancelled. Nothing was saved.")
        return

    samples, problems = collect_samples(sequence.accepted_frames, results)
    absent = missing_steps(samples)
    live_flags = [r.is_live for r in results if r.embedding is not None]
    ok, messages = capture_save_verdict(problems, absent, live_flags, liveness_enabled=args.liveness)
    if not ok:
        print("Capture was not saved:")
        for message in messages:
            print(f"  - {message}")
        raise SystemExit(1)

    if args.stop_file and args.stop_file.exists():
        print("Cancelled. Nothing was saved.")
        return
    with SessionLocal() as session:
        student = get_or_create_student(session, args.student_no, args.name, args.exam, commit=False)
        save_capture_samples(session, student.id, samples)
    print(f"Saved {len(samples)} face samples for {full_name} ({args.student_no}).")


if __name__ == "__main__":
    main()
