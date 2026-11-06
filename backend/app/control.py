"""PC-only demo controls. Secret is shared with the local Next server, never the browser."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from collections import deque
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.cleanup import CleanupPlan, execute_cleanup
from app.config import DATA_DIR, BASE_DIR, SUPABASE_URL, SUPABASE_SERVICE_KEY, ENROLL_MODEL
from app.db import get_session
from app.demo import demo_exam
from app.eligibility import check_eligibility
from app.live import LiveStore
from app.models import AttendanceRecord, Exam, FaceEmbedding, Registration, Student

router = APIRouter(prefix="/control", tags=["local demo controls"])
KEY_FILE = DATA_DIR / "control.key"


def control_key():
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        value = KEY_FILE.read_text().strip()
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise HTTPException(503, "Local control key is invalid; restore or regenerate it while the API is stopped")
        return value
    value = secrets.token_hex(32)
    with os.fdopen(fd, "w") as output:
        output.write(value)
    return value


def authorize(x_local_control: str = Header(default="")):
    if not hmac.compare_digest(x_local_control, control_key()):
        raise HTTPException(403, "Local control authorization required")


class Jobs:
    def __init__(self):
        self.lock = threading.RLock()
        self.process = None
        self.kind = None
        self.lines = deque(maxlen=60)
        self.code = None
        self.camera_info = None
        self.stop_path = DATA_DIR / "camera.stop"

    def status(self):
        running = self.process is not None and self.process.poll() is None
        return {"running": running, "kind": self.kind,
                "exit_code": None if running else (self.process.poll() if self.process else self.code), "log": list(self.lines),
                "sync_configured": bool(SUPABASE_URL and SUPABASE_SERVICE_KEY), "platform": sys.platform, "camera_info": self.camera_info}

    def idle(self):
        if self.process is not None and self.process.poll() is None:
            raise HTTPException(409, "Stop/wait for the current demo task first")
        if LiveStore().read()["status"] in ("running", "starting", "disconnected"):
            raise HTTPException(409, "Close the existing camera session before changing the gallery or starting another task")

    def start(self, kind, args):
        self.idle()
        self.lines.clear()
        self.code = None
        if kind in ("camera", "local_enroll"):
            self.stop_path.unlink(missing_ok=True)
        try:
            self.process = subprocess.Popen([sys.executable, "-u", "-m", *args], cwd=BASE_DIR,
                                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            text=True, encoding="utf-8", errors="replace", shell=False)
        except OSError as exc:
            raise HTTPException(503, "Unable to launch the local demo process") from exc
        self.kind = kind
        self._launch_reader(self.process)

    def _launch_timeout(self, process):
        def expire():
            with self.lock:
                if process.poll() is None:
                    self.lines.append("CAMERA CHECK TIMED OUT: device/driver did not respond; close the DroidCam client and reconnect it before retrying.")
                    process.kill()
        timer = threading.Timer(20, expire)
        timer.daemon = True
        timer.start()

    def _launch_reader(self, process):
        threading.Thread(target=self._collect, args=(process,), daemon=True).start()

    def _collect(self, process):
        for line in process.stdout:
            with self.lock:
                # Never return a configured service key to the browser via logs.
                self.lines.append(line.rstrip().replace(SUPABASE_SERVICE_KEY, "[redacted]") if SUPABASE_SERVICE_KEY else line.rstrip())
        code = process.wait()
        with self.lock:
            self.code = code
        process.stdout.close()


jobs = Jobs()
plans = {}


class ExamSelection(BaseModel):
    exam_id: int


class CameraDevice(BaseModel):
    camera: int = Field(default=0, ge=0, le=10)
    source: Literal["pc", "droidcam"] = "pc"
    capture_backend: Literal["auto", "dshow", "msmf"] = "auto"


class CameraSelection(CameraDevice):
    exam_id: int | None = None
    demo_mode: bool = False
    demo_classroom: bool = False


def camera_args(body: CameraDevice):
    if body.capture_backend != "auto" and sys.platform != "win32":
        raise HTTPException(422, "This capture backend is Windows-only; choose Automatic")
    args = ["--camera", str(body.camera)]
    if body.source != "pc" or body.capture_backend != "auto":
        args += ["--camera-source", body.source, "--capture-backend", body.capture_backend]
    return args


class PeopleSelection(BaseModel):
    student_nos: list[str] = Field(min_length=1, max_length=500)


class RegisterSelection(PeopleSelection, ExamSelection):
    pass


class DeleteConfirmation(BaseModel):
    token: str
    confirmation: str


def get_exam(session, exam_id):
    exam = session.get(Exam, exam_id)
    if exam is None:
        raise HTTPException(404, "Exam not found")
    return exam


def selected_people(session, numbers):
    people = session.scalars(select(Student).where(Student.student_no.in_(set(numbers))).order_by(Student.student_no)).all()
    if len(people) != len(set(numbers)):
        raise HTTPException(409, "Some selected students no longer exist; refresh the list")
    return people


def fingerprint(session, people):
    ids = [p.id for p in people]
    rows = {"people": [(p.id, p.student_no, p.full_name) for p in people]}
    counts = {}
    for model, label in [(FaceEmbedding, "embeddings"), (Registration, "registrations"), (AttendanceRecord, "attendance")]:
        values = list(session.scalars(select(model.id).where(model.student_id.in_(ids)).order_by(model.id)))
        rows[label] = values
        counts[label] = len(values)
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest(), counts


@router.get("/status", dependencies=[Depends(authorize)])
def status():
    with jobs.lock:
        return jobs.status()


@router.get("/readiness", dependencies=[Depends(authorize)])
def readiness(exam_id: int | None = None, demo: bool = False, session: Session = Depends(get_session)):
    if not demo:
        get_exam(session, exam_id)
    registered = set(session.scalars(select(Registration.student_id).where(Registration.exam_id == exam_id)))
    result = []
    for person in session.scalars(select(Student).order_by(Student.student_no)):
        samples = len(list(session.scalars(select(FaceEmbedding.id).where(FaceEmbedding.student_id == person.id))))
        eligible = check_eligibility(registered=person.id in registered, fees_cleared=person.fees_cleared, suspended=person.suspended)
        reasons = ([] if demo else eligible.reasons) + ([] if samples else ["No face samples — sync/enroll first"])
        result.append({"student_no": person.student_no, "full_name": person.full_name,
                       "face_samples": samples, "registered": person.id in registered,
                       "ready": not reasons, "reasons": reasons})
    return result


@router.post("/camera/start", dependencies=[Depends(authorize)])
def start_camera(body: CameraSelection, session: Session = Depends(get_session)):
    with jobs.lock:
        jobs.idle()
        exam = demo_exam(session, create=True) if body.demo_mode else get_exam(session, body.exam_id)
        jobs.start("camera", ["app.vision.attend", "--exam", exam.course_code, *camera_args(body),
                              "--det-size", "480", "--threads", "4", "--model", ENROLL_MODEL, "--stop-file", str(jobs.stop_path),
                              *(["--demo-classroom"] if body.demo_classroom else []), *(["--demo-mode"] if body.demo_mode else [])])
        jobs.camera_info = body.model_dump(exclude={"exam_id"})
        return jobs.status()


@router.post("/camera/check", dependencies=[Depends(authorize)])
def check_camera(body: CameraDevice):
    with jobs.lock:
        args = camera_args(body)
        jobs.start("camera_check", ["app.vision.camera_check", *args])
        jobs.camera_info = body.model_dump()
        jobs._launch_timeout(jobs.process)
        return jobs.status()


@router.post("/camera/stop", dependencies=[Depends(authorize)])
def stop_camera():
    with jobs.lock:
        if jobs.process is None or jobs.process.poll() is not None or jobs.kind not in ("camera", "local_enroll"):
            raise HTTPException(409, "No dashboard-started camera task to stop; close an external camera window with q")
        # Cooperative stop lets attendance flush stopped state and release the camera.
        jobs.stop_path.write_text("stop")
        return {"message": "Stop requested; camera will close after the current inference/model load"}


@router.post("/sync", dependencies=[Depends(authorize)])
def sync(body: ExamSelection, session: Session = Depends(get_session)):
    with jobs.lock:
        exam = get_exam(session, body.exam_id)
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            raise HTTPException(409, "Configure Supabase secrets on the backend PC first; never enter the service key into the dashboard")
        jobs.start("sync", ["app.sync", "--exam", exam.course_code])
        return jobs.status()


@router.post("/register", dependencies=[Depends(authorize)])
def register(body: RegisterSelection, session: Session = Depends(get_session)):
    with jobs.lock:
        jobs.idle()
        exam = get_exam(session, body.exam_id)
        people = selected_people(session, body.student_nos)
        existing = set(session.scalars(select(Registration.student_id).where(Registration.exam_id == exam.id)))
        for person in people:
            if person.id not in existing:
                session.add(Registration(student_id=person.id, exam_id=exam.id))
        session.commit()
        return {"registered": len(people), "message": "Registration updated; fee/suspension rules were not changed"}


@router.post("/delete/preview", dependencies=[Depends(authorize)])
def preview_delete(body: PeopleSelection, session: Session = Depends(get_session)):
    with jobs.lock:
        jobs.idle()
        people = selected_people(session, body.student_nos)
        digest, counts = fingerprint(session, people)
        token = secrets.token_urlsafe(32)
        now = time.monotonic()
        for key in list(plans):
            if plans[key][0] < now:
                del plans[key]
        if len(plans) >= 100:
            plans.clear()
        plans[token] = (now + 120, [p.student_no for p in people], digest)
        return {"token": token, "students": [{"student_no": p.student_no, "full_name": p.full_name} for p in people],
                "counts": counts, "expires_in": 120,
                "warning": "Local deletion only. Supabase inbox submissions are NOT removed and could be synced again. Exams are preserved."}


@router.post("/delete/confirm", dependencies=[Depends(authorize)])
def confirm_delete(body: DeleteConfirmation, session: Session = Depends(get_session)):
    with jobs.lock:
        jobs.idle()
        if body.confirmation != "DELETE":
            raise HTTPException(400, "Type DELETE to confirm")
        plan = plans.pop(body.token, None)
        if plan is None or plan[0] < time.monotonic():
            raise HTTPException(409, "Preview expired; review the deletion again")
        try:
            # The demo uses SQLite. Reserve the writer before checking the preview
            # fingerprint so another enrollment cannot change rows mid-confirmation.
            if session.get_bind().dialect.name == "sqlite":
                session.execute(text("BEGIN IMMEDIATE"))
            people = selected_people(session, plan[1])
            digest, _ = fingerprint(session, people)
            if digest != plan[2]:
                raise HTTPException(409, "Records changed since preview; review the deletion again")
            counts = execute_cleanup(session, CleanupPlan(kept=[], removed=people))
        except Exception:
            session.rollback()
            raise
        return {"deleted": counts.students, "message": "Selected students and their local face samples, registrations and attendance were removed. Exams preserved."}

# Short-lived, one-use previews for the three presentation actions.
presentation_plans = {}


class PresentationSelection(ExamSelection):
    action: Literal["register_all", "clear_attendance", "reset_display"]


def presentation_snapshot(session, body):
    get_exam(session, body.exam_id)
    classroom = session.scalar(select(Exam).where(Exam.course_code == "CS101")) or session.scalar(select(Exam).order_by(Exam.starts_at))
    if classroom.id != body.exam_id:
        raise HTTPException(409, "Classroom backing exam changed; refresh the controls")
    if body.action == "register_all":
        students = list(session.scalars(select(Student.id).order_by(Student.id)))
        registered = list(session.scalars(select(Registration.student_id).where(Registration.exam_id == body.exam_id).order_by(Registration.student_id)))
        return {"students": students, "registered": registered}, {"volunteers": len(students), "new_registrations": len(set(students) - set(registered))}
    if body.action == "clear_attendance":
        ids = [tuple(row) for row in session.execute(select(AttendanceRecord.id, AttendanceRecord.student_id, AttendanceRecord.recorded_at, AttendanceRecord.confidence, AttendanceRecord.source).where(AttendanceRecord.exam_id == body.exam_id).order_by(AttendanceRecord.id))]
        return ids, {"attendance_records": len(ids)}
    live = LiveStore().read()
    return [live.get(k) for k in ("session_id", "updated_at", "latest_event_id")], {"activity_events": len(live.get("events", [])), "identified_count": live.get("identified_count", 0)}


@router.post("/presentation/preview", dependencies=[Depends(authorize)])
def preview_presentation(body: PresentationSelection, session: Session = Depends(get_session)):
    with jobs.lock:
        jobs.idle()
        snapshot, counts = presentation_snapshot(session, body)
        now = time.monotonic()
        for token in list(presentation_plans):
            if presentation_plans[token][0] < now:
                del presentation_plans[token]
        if len(presentation_plans) >= 100:
            presentation_plans.clear()
        token = secrets.token_urlsafe(32)
        presentation_plans[token] = (now + 120, body, snapshot)
        return {"token": token, "action": body.action, "counts": counts, "expires_in": 120}


@router.post("/presentation/confirm", dependencies=[Depends(authorize)])
def confirm_presentation(body: DeleteConfirmation, session: Session = Depends(get_session)):
    with jobs.lock:
        jobs.idle()
        if body.confirmation != "CONFIRM":
            raise HTTPException(400, "Confirm the presentation action")
        plan = presentation_plans.pop(body.token, None)
        if plan is None or plan[0] < time.monotonic():
            raise HTTPException(409, "Preview expired; review the action again")
        selection, expected = plan[1:]
        try:
            if session.get_bind().dialect.name == "sqlite":
                session.execute(text("BEGIN IMMEDIATE"))
            snapshot, counts = presentation_snapshot(session, selection)
            if snapshot != expected:
                raise HTTPException(409, "Records changed; review the action again")
            if selection.action == "register_all":
                for student_id in set(snapshot["students"]) - set(snapshot["registered"]):
                    session.add(Registration(student_id=student_id, exam_id=selection.exam_id))
                message = f'Registered volunteers: {counts["new_registrations"]} new registrations. Eligibility flags unchanged.'
            elif selection.action == "clear_attendance":
                from sqlalchemy import delete
                session.execute(delete(AttendanceRecord).where(AttendanceRecord.exam_id == selection.exam_id))
                message = f'Cleared {counts["attendance_records"]} classroom attendance records. Students, faces and registrations preserved. Start recognition for a fresh round.'
            else:
                LiveStore().reset_display(expected)
                message = "Live display reset. Saved attendance unchanged."
            session.commit()
        except Exception:
            session.rollback()
            raise
        return {"message": message}


class LocalEnrollment(CameraDevice):
    model_config = {"str_strip_whitespace": True}
    student_no: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9/_-]+$")
    full_name: str = Field(min_length=1, max_length=120, pattern=r"^[^\x00-\x1f\x7f]+$")
    replace_existing: bool = False


@router.post("/demo/enroll", dependencies=[Depends(authorize)])
def local_enrollment(body: LocalEnrollment, session: Session = Depends(get_session)):
    with jobs.lock:
        jobs.idle()
        args = camera_args(body)
        number = body.student_no.upper()
        existing = session.scalar(select(Student).where(Student.student_no == number))
        if existing is not None and not body.replace_existing:
            raise HTTPException(409, "This index already exists. Confirm re-enrollment to replace its local capture samples.")
        jobs.start("local_enroll", ["app.vision.capture", f"--student-no={number}", f"--name={body.full_name}",
                                  *args, "--model", ENROLL_MODEL, "--det-size", "480", "--threads", "4",
                                  "--stop-file", str(jobs.stop_path)])
        jobs.camera_info = body.model_dump(include={"camera", "source", "capture_backend"})
        return jobs.status()


@router.post("/demo/sync", dependencies=[Depends(authorize)])
def demo_sync(session: Session = Depends(get_session)):
    with jobs.lock:
        jobs.idle()
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            raise HTTPException(409, "Online sync is not configured. Use Enroll locally instead.")
        # Recognition demonstration never requires exam registration, including submissions
        # naming a different exam. Preserve the existing cloud inbox sync behavior.
        exam = demo_exam(session, create=True)
        jobs.start("sync", ["app.sync", "--exam", exam.course_code])
        return jobs.status()


def demo_reset_snapshot(session, exam_id):
    records = [tuple(row) for row in session.execute(select(AttendanceRecord.id, AttendanceRecord.student_id, AttendanceRecord.recorded_at, AttendanceRecord.source).where(AttendanceRecord.exam_id == exam_id).order_by(AttendanceRecord.id))]
    live = LiveStore().read()
    version = [live.get(k) for k in ("session_id", "updated_at", "latest_event_id")]
    return (records, version), {"attendance_records": len(records), "activity_events": len(live.get("events", [])), "identified_count": live.get("identified_count", 0)}


demo_reset_plans = {}


@router.post("/demo/reset/preview", dependencies=[Depends(authorize)])
def preview_demo_reset(session: Session = Depends(get_session)):
    with jobs.lock:
        jobs.idle()
        exam = demo_exam(session, create=True)
        snapshot, counts = demo_reset_snapshot(session, exam.id)
        now = time.monotonic()
        for token in list(demo_reset_plans):
            if demo_reset_plans[token][0] < now:
                del demo_reset_plans[token]
        if len(demo_reset_plans) >= 100:
            demo_reset_plans.clear()
        token = secrets.token_urlsafe(32)
        demo_reset_plans[token] = (now + 120, exam.id, snapshot)
        return {"token": token, "counts": counts, "expires_in": 120}


@router.post("/demo/reset/confirm", dependencies=[Depends(authorize)])
def confirm_demo_reset(body: DeleteConfirmation, session: Session = Depends(get_session)):
    from sqlalchemy import delete
    with jobs.lock:
        jobs.idle()
        if body.confirmation != "RESET":
            raise HTTPException(400, "Confirm the demonstration reset")
        plan = demo_reset_plans.pop(body.token, None)
        if plan is None or plan[0] < time.monotonic():
            raise HTTPException(409, "Preview expired; review the reset again")
        try:
            if session.get_bind().dialect.name == "sqlite":
                session.execute(text("BEGIN IMMEDIATE"))
            snapshot, _ = demo_reset_snapshot(session, plan[1])
            if snapshot != plan[2]:
                raise HTTPException(409, "Demonstration changed; review the reset again")
            # Check ownership under the live store's own write lock before touching attendance.
            LiveStore().reset_display(snapshot[1], exam_id=plan[1], demo_mode=True)
            session.execute(delete(AttendanceRecord).where(AttendanceRecord.exam_id == plan[1]))
            session.commit()
        except Exception:
            session.rollback()
            raise
        return {"message": "Demonstration reset: attendance, activity and live counters cleared. Enrolled faces preserved. Click Start recognition for the next round."}
