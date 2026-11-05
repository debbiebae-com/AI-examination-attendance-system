"""Guided face capture for one person: look straight, turn left, turn right, blink.

Runs in a window on the PC with the webcam. Each accepted frame is stored as a face embedding
for the student, replacing any earlier capture for that student.

Run from backend/ after installing the vision extra:

    uv run --extra vision python -m app.vision.capture --student-no VOL-001 --name "Ama Mensah"

Options:
    --exam CODE       also register the student for this exam (e.g. CS101)
    --left-sign -1    use if turning to your left never completes (flips the camera's yaw sign)
    --camera 1        use if the wrong camera opens

Press q in the window to cancel.
"""

import argparse

import cv2
from sqlalchemy import select

from app.db import SessionLocal, engine
from app.models import Base, Exam, Registration, Student
from app.vision.capture_flow import PROMPTS, STEPS, CaptureSequence, FrameSignal
from app.vision.embedder import DetectedFace, InsightFaceEmbedder
from app.vision.gallery import save_capture_samples

FONT = cv2.FONT_HERSHEY_SIMPLEX
WINDOW = "Face capture (press q to cancel)"


def get_or_create_student(session, student_no: str, name: str | None, exam_code: str | None) -> Student:
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

    session.commit()
    return student


def to_signal(faces: list[DetectedFace]) -> FrameSignal:
    if len(faces) != 1:
        return FrameSignal(face_count=len(faces))
    face = faces[0]
    return FrameSignal(
        face_count=1,
        det_score=face.score,
        is_live=face.is_live,
        yaw=face.pose[1] if face.pose is not None else None,
        eye_ratio=face.eye_ratio,
        embedding=face.embedding,
    )


def draw_overlay(image, faces: list[DetectedFace], sequence: CaptureSequence, message: str, signal: FrameSignal) -> None:
    for face in faces:
        x1, y1, x2, y2 = (int(v) for v in face.bbox)
        cv2.rectangle(image, (x1, y1), (x2, y2), (0, 200, 0), 2)

    step = sequence.current_step
    cv2.putText(image, PROMPTS[step] if step else "Done", (20, 40), FONT, 0.9, (255, 255, 255), 2)
    if message:
        cv2.putText(image, message, (20, 75), FONT, 0.7, (0, 0, 255), 2)

    y = 115
    for name in STEPS:
        got, need = sequence.progress(name)
        cv2.putText(image, f"{name:<9} {got}/{need}", (20, y), FONT, 0.6, (255, 255, 255), 2)
        y += 28

    details = []
    if signal.yaw is not None:
        details.append(f"yaw {signal.yaw:+.0f}")
    if signal.eye_ratio is not None:
        details.append(f"eyes {signal.eye_ratio:.2f}")
    if details:
        cv2.putText(image, "  ".join(details), (20, y + 10), FONT, 0.6, (200, 200, 200), 2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--student-no", required=True)
    parser.add_argument("--name", help="full name, used only when creating a new student")
    parser.add_argument("--exam", help="course code to register the student for")
    parser.add_argument("--left-sign", type=int, choices=[1, -1], default=1)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--samples", type=int, default=3, help="frames to keep per turn or straight step")
    args = parser.parse_args()

    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        student = get_or_create_student(session, args.student_no, args.name, args.exam)
        student_id, full_name = student.id, student.full_name

    print("Loading InsightFace with the liveness check (the first run downloads the models)...")
    embedder = InsightFaceEmbedder(liveness=True)

    camera = cv2.VideoCapture(args.camera)
    if not camera.isOpened():
        raise SystemExit(f"Cannot open camera {args.camera}. Try --camera 1.")

    sequence = CaptureSequence(left_sign=args.left_sign, samples_per_step=args.samples)
    cancelled = False
    try:
        while not sequence.done:
            ok, image = camera.read()
            if not ok:
                raise SystemExit("The camera stopped sending frames.")
            image = cv2.flip(image, 1)  # mirror the view so movements feel natural
            faces = embedder.analyse(image)
            signal = to_signal(faces)
            message = sequence.process(signal)
            draw_overlay(image, faces, sequence, message, signal)
            cv2.imshow(WINDOW, image)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                cancelled = True
                break
    finally:
        camera.release()
        cv2.destroyAllWindows()

    if cancelled or not sequence.done:
        print("Cancelled. Nothing was saved.")
        return

    with SessionLocal() as session:
        save_capture_samples(session, student_id, sequence.samples)
    print(f"Saved {len(sequence.samples)} face samples for {full_name} ({args.student_no}).")


if __name__ == "__main__":
    main()
