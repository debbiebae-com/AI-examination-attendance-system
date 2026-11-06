from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func

from app import control
from app.db import get_session
from app.main import app
from app.models import Student, Exam, Registration, AttendanceRecord, FaceEmbedding


@pytest.fixture
def api(session, tmp_path, monkeypatch):
    monkeypatch.setattr(control, "KEY_FILE", tmp_path / "control.key")
    monkeypatch.setattr(control, "LiveStore", lambda: SimpleNamespace(read=lambda: {"status": "idle"}))
    manager = control.Jobs()
    manager.stop_path = tmp_path / "camera.stop"
    monkeypatch.setattr(control, "jobs", manager)
    monkeypatch.setattr(control, "plans", {})
    monkeypatch.setattr(control, "presentation_plans", {})
    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app)
    client.headers["X-Local-Control"] = control.control_key()
    yield client
    app.dependency_overrides.clear()


def test_control_requires_server_secret(api):
    assert api.get("/control/status", headers={"X-Local-Control": "wrong"}).status_code == 403
    assert api.get("/control/status").status_code == 200


def test_readiness_lists_unready_volunteers(api, session):
    exam = session.scalar(select(Exam))
    response = api.get(f"/control/readiness?exam_id={exam.id}")
    assert response.status_code == 200
    assert len(response.json()) == 20
    assert "No face samples" in " ".join(response.json()[0]["reasons"])


def test_registration_is_idempotent_and_does_not_clear_eligibility_flags(api, session):
    exam = session.scalar(select(Exam).where(Exam.course_code == "CS101"))
    payload = {"exam_id": exam.id, "student_nos": ["UGS-26-020"]}
    assert api.post("/control/register", json=payload).status_code == 200
    assert api.post("/control/register", json=payload).status_code == 200
    student = session.scalar(select(Student).where(Student.student_no == "UGS-26-020"))
    assert session.scalar(select(func.count(Registration.id)).where(Registration.student_id == student.id, Registration.exam_id == exam.id)) == 1
    assert api.post("/control/register", json={**payload,"student_nos":["missing"]}).status_code == 409


def test_delete_preview_then_confirmation_preserves_exams_and_other_people(api, session):
    from app.attendance import mark_attendance
    exam = session.scalar(select(Exam).where(Exam.course_code == "CS101"))
    student = session.scalar(select(Student).where(Student.student_no == "UGS-26-001"))
    session.add(FaceEmbedding(student_id=student.id, embedding=b"test", source_photo="test", det_score=1))
    session.commit()
    mark_attendance(session, exam_id=exam.id, student_no=student.student_no)
    response = api.post("/control/delete/preview", json={"student_nos": [student.student_no]})
    plan = response.json()
    assert plan["counts"]["embeddings"] == 1
    assert plan["counts"]["attendance"] == 1
    assert session.scalar(select(func.count(Student.id))) == 20
    session.rollback()  # End this test-side read transaction before the write reservation.
    assert api.post("/control/delete/confirm", json={"token":plan["token"], "confirmation":"no"}).status_code == 400
    result = api.post("/control/delete/confirm", json={"token":plan["token"], "confirmation":"DELETE"})
    assert result.status_code == 200, result.text
    assert result.json()["deleted"] == 1
    assert session.scalar(select(func.count(Student.id))) == 19
    assert session.scalar(select(func.count(Exam.id))) == 2
    assert session.scalar(select(func.count(FaceEmbedding.id))) == 0
    session.rollback()
    assert api.post("/control/delete/confirm", json={"token":plan["token"], "confirmation":"DELETE"}).status_code == 409


def test_changed_record_invalidates_delete_preview(api, session):
    plan = api.post("/control/delete/preview",json={"student_nos":["UGS-26-001"]}).json()
    student = session.scalar(select(Student).where(Student.student_no == "UGS-26-001"))
    student.full_name = "Changed name"
    session.commit()
    response = api.post("/control/delete/confirm",json={"token":plan["token"],"confirmation":"DELETE"})
    assert response.status_code == 409
    assert session.scalar(select(func.count(Student.id))) == 20


def test_active_camera_blocks_gallery_changes(api, monkeypatch):
    monkeypatch.setattr(control, "LiveStore", lambda: SimpleNamespace(read=lambda:{"status":"running"}))
    assert api.post("/control/delete/preview",json={"student_nos":["UGS-26-001"]}).status_code == 409
    assert api.post("/control/register",json={"exam_id":1,"student_nos":["UGS-26-001"]}).status_code == 409


def test_unknown_or_empty_selection_does_not_delete(api):
    assert api.post("/control/delete/preview",json={"student_nos":[]}).status_code == 422
    assert api.post("/control/delete/preview",json={"student_nos":["nobody"]}).status_code == 409
    assert api.post("/control/delete/confirm",json={"token":"invalid","confirmation":"DELETE"}).status_code == 409


def test_start_uses_fixed_argv_and_stop_is_cooperative(api, monkeypatch):
    calls=[]
    class Process:
        stdout=[]
        def poll(self): return None
    monkeypatch.setattr(control.subprocess,"Popen",lambda args,**kwargs:(calls.append((args,kwargs)) or Process()))
    monkeypatch.setattr(control.Jobs,"_launch_reader",lambda self, process:None)
    result=api.post("/control/camera/start",json={"exam_id":1,"camera":1})
    assert result.status_code == 200
    assert result.json()["running"]
    assert calls[0][1]["shell"] is False
    assert calls[0][0][1:4] == ["-u","-m","app.vision.attend"]
    assert api.post("/control/camera/start",json={"exam_id":1}).status_code == 409
    assert api.post("/control/camera/stop",json={}).status_code == 200
    assert control.jobs.stop_path.exists()


def test_unconfigured_sync_and_external_camera_stop_fail_safely(api,monkeypatch):
    monkeypatch.setattr(control,"SUPABASE_URL","")
    monkeypatch.setattr(control,"SUPABASE_SERVICE_KEY","")
    assert api.post("/control/sync",json={"exam_id":1}).status_code == 409
    assert api.post("/control/camera/stop",json={}).status_code == 409


def test_empty_control_key_fails_closed(api):
    control.KEY_FILE.write_text("")
    assert api.get("/control/status", headers={"X-Local-Control":""}).status_code == 503


def test_phone_camera_check_is_authorized_bounded_and_does_not_need_exam(api, monkeypatch):
    calls=[];timeouts=[]
    class Process:
        stdout=[]
        def poll(self): return None
    monkeypatch.setattr(control,"sys",SimpleNamespace(platform="win32",executable="python"))
    monkeypatch.setattr(control.subprocess,"Popen",lambda args,**kwargs:(calls.append((args,kwargs)) or Process()))
    monkeypatch.setattr(control.Jobs,"_launch_reader",lambda self,process:None)
    monkeypatch.setattr(control.Jobs,"_launch_timeout",lambda self,process:timeouts.append(process))
    payload={"camera":2,"source":"droidcam","capture_backend":"dshow"}
    assert api.post("/control/camera/check",json=payload,headers={"X-Local-Control":"bad"}).status_code==403
    result=api.post("/control/camera/check",json=payload)
    assert result.status_code==200
    assert result.json()["kind"]=="camera_check"
    assert result.json()["camera_info"]==payload
    assert calls[0][0][3:]==["app.vision.camera_check","--camera","2","--camera-source","droidcam","--capture-backend","dshow"]
    assert calls[0][1]["shell"] is False and len(timeouts)==1
    assert api.post("/control/camera/start",json={"exam_id":1}).status_code==409
    assert api.post("/control/camera/check",json=payload).status_code==409


def test_camera_device_validation_and_no_network_urls(api, monkeypatch):
    monkeypatch.setattr(control,"sys",SimpleNamespace(platform="linux",executable="python"))
    for payload in ({"camera":-1},{"camera":11},{"camera":"http://phone:4747/video"},{"camera":1,"source":"internet"},{"camera":1,"capture_backend":"shell"},{"camera":1,"capture_backend":"dshow"}):
        assert api.post("/control/camera/check",json=payload).status_code==422


def test_phone_recognition_preserves_identity_and_performance_settings(api, monkeypatch):
    calls=[]
    class Process:
        stdout=[]
        def poll(self): return None
    monkeypatch.setattr(control,"sys",SimpleNamespace(platform="win32",executable="python"))
    monkeypatch.setattr(control.subprocess,"Popen",lambda args,**kwargs:(calls.append(args) or Process()))
    monkeypatch.setattr(control.Jobs,"_launch_reader",lambda self,process:None)
    result=api.post("/control/camera/start",json={"exam_id":1,"camera":2,"source":"droidcam","capture_backend":"msmf"})
    assert result.status_code==200
    argv=calls[0]
    for flag,value in (("--camera","2"),("--camera-source","droidcam"),("--capture-backend","msmf"),("--det-size","480"),("--threads","4"),("--model",control.ENROLL_MODEL)):
        assert argv[argv.index(flag)+1]==value


def test_camera_check_timeout_only_kills_the_checked_process(monkeypatch):
    callbacks=[];killed=[]
    timer=SimpleNamespace(daemon=False,start=lambda:None)
    def create_timer(seconds,callback):
        assert seconds==20
        callbacks.append(callback)
        return timer
    monkeypatch.setattr(control.threading,"Timer",create_timer)
    manager=control.Jobs()
    process=SimpleNamespace(poll=lambda:None,kill=lambda:killed.append("checked"))
    manager._launch_timeout(process)
    assert timer.daemon
    callbacks[0]()
    assert killed==["checked"] and "TIMED OUT" in manager.lines[-1]
    done=SimpleNamespace(poll=lambda:0,kill=lambda:killed.append("finished"))
    manager._launch_timeout(done)
    callbacks[1]()
    assert killed==["checked"]


def test_classroom_mode_is_an_overlay_flag_not_a_new_exam(api, session, monkeypatch):
    calls=[]
    class Process:
        stdout=[]
        def poll(self): return None
    monkeypatch.setattr(control.subprocess,"Popen",lambda args,**kwargs:(calls.append(args) or Process()))
    monkeypatch.setattr(control.Jobs,"_launch_reader",lambda self,process:None)
    before=session.scalar(select(func.count(Exam.id)))
    result=api.post("/control/camera/start",json={"exam_id":1,"camera":0,"demo_classroom":True})
    assert result.status_code==200
    assert "--demo-classroom" in calls[0]
    assert "--exam" in calls[0] and "--det-size" in calls[0]
    assert session.scalar(select(func.count(Exam.id)))==before


def presentation_preview(api, session, action):
    exam = session.scalar(select(Exam).where(Exam.course_code == "CS101"))
    exam_id = exam.id
    session.rollback()
    response = api.post("/control/presentation/preview", json={"exam_id": exam_id, "action": action})
    assert response.status_code == 200, response.text
    return response.json()


def presentation_confirm(api, plan):
    return api.post("/control/presentation/confirm", json={"token": plan["token"], "confirmation": "CONFIRM"})


def test_presentation_register_all_is_previewed_idempotent_and_preserves_flags(api, session):
    flags = list(session.execute(select(Student.id, Student.fees_cleared, Student.suspended)))
    plan = presentation_preview(api, session, "register_all")
    assert plan["counts"]["volunteers"] == 20
    assert presentation_confirm(api, plan).status_code == 200
    assert list(session.execute(select(Student.id, Student.fees_cleared, Student.suspended))) == flags
    again = presentation_preview(api, session, "register_all")
    assert again["counts"]["new_registrations"] == 0
    assert presentation_confirm(api, again).status_code == 200
    assert presentation_confirm(api, again).status_code == 409


def test_classroom_clear_preserves_everything_else_and_allows_repeat_attendance(api, session):
    from app.attendance import mark_attendance
    exams = list(session.scalars(select(Exam).order_by(Exam.id)))
    classroom = next(e for e in exams if e.course_code == "CS101")
    other = next(e for e in exams if e.id != classroom.id)
    person = session.scalar(select(Student).where(Student.student_no == "UGS-26-001"))
    if not session.scalar(select(Registration).where(Registration.exam_id == other.id, Registration.student_id == person.id)):
        session.add(Registration(exam_id=other.id, student_id=person.id))
    session.add(FaceEmbedding(student_id=person.id, embedding=b"test", source_photo="test", det_score=1))
    session.commit()
    mark_attendance(session, exam_id=classroom.id, student_no=person.student_no)
    mark_attendance(session, exam_id=other.id, student_no=person.student_no)
    classroom_id, other_id, student_no = classroom.id, other.id, person.student_no
    counts = [session.scalar(select(func.count(model.id))) for model in (Student, Registration, FaceEmbedding, Exam)]
    plan = presentation_preview(api, session, "clear_attendance")
    assert plan["counts"] == {"attendance_records": 1}
    assert session.scalar(select(func.count(AttendanceRecord.id))) == 2
    session.rollback()
    assert presentation_confirm(api, plan).status_code == 200
    assert session.scalar(select(func.count(AttendanceRecord.id)).where(AttendanceRecord.exam_id == classroom_id)) == 0
    assert session.scalar(select(func.count(AttendanceRecord.id)).where(AttendanceRecord.exam_id == other_id)) == 1
    assert [session.scalar(select(func.count(model.id))) for model in (Student, Registration, FaceEmbedding, Exam)] == counts
    _, created = mark_attendance(session, exam_id=classroom_id, student_no=student_no, source="camera")
    assert created


@pytest.mark.parametrize("action", ["register_all", "clear_attendance", "reset_display"])
def test_presentation_refuses_active_recognition_or_task(api, session, monkeypatch, action):
    plan = presentation_preview(api, session, action)
    monkeypatch.setattr(control, "LiveStore", lambda: SimpleNamespace(read=lambda: {"status": "running"}))
    assert presentation_confirm(api, plan).status_code == 409
    assert api.post("/control/presentation/preview", json={"exam_id": 1, "action": action}).status_code == 409
    monkeypatch.setattr(control, "LiveStore", lambda: SimpleNamespace(read=lambda: {"status": "idle"}))
    control.jobs.process = SimpleNamespace(poll=lambda: None)
    assert presentation_confirm(api, plan).status_code == 409


def test_presentation_rejects_changed_expired_unconfirmed_or_wrong_scope(api, session, monkeypatch):
    plan = presentation_preview(api, session, "clear_attendance")
    assert api.post("/control/presentation/confirm", json={"token": plan["token"], "confirmation": "no"}).status_code == 400
    from app.attendance import mark_attendance
    mark_attendance(session, exam_id=1, student_no="UGS-26-001")
    assert presentation_confirm(api, plan).status_code == 409
    plan = presentation_preview(api, session, "register_all")
    session.add(Student(student_no="NEW", full_name="New volunteer", programme="Computer Science", level=300, fees_cleared=True, suspended=False))
    session.commit()
    assert presentation_confirm(api, plan).status_code == 409
    plan = presentation_preview(api, session, "register_all")
    expiry, selection, snapshot = control.presentation_plans[plan["token"]]
    control.presentation_plans[plan["token"]] = (0, selection, snapshot)
    assert presentation_confirm(api, plan).status_code == 409
    assert api.post("/control/presentation/preview", json={"exam_id": 2, "action": "clear_attendance"}).status_code == 409
    assert api.post("/control/presentation/preview", json={"exam_id": 1, "action": "delete_everything"}).status_code == 422
    assert api.post("/control/presentation/preview", json={"exam_id": 1, "action": "clear_attendance"}, headers={"X-Local-Control": "wrong"}).status_code == 403


def test_presentation_reset_preserves_saved_attendance(api, session, monkeypatch, tmp_path):
    from app.live import LiveStore, LivePublisher
    from app.attendance import mark_attendance
    store = LiveStore(tmp_path / "live.db")
    monkeypatch.setattr(control, "LiveStore", lambda: store)
    mark_attendance(session, exam_id=1, student_no="UGS-26-001")
    with LivePublisher(1, store=store) as live:
        live.payload.update(demo_classroom=True, classroom_name="Test classroom 1")
        live.event("identified", student_no="UGS-26-001")
    plan = presentation_preview(api, session, "reset_display")
    assert plan["counts"] == {"activity_events": 2, "identified_count": 1}
    assert presentation_confirm(api, plan).status_code == 200
    snapshot = store.read()
    assert snapshot["events"] == []
    assert snapshot["identified_count"] == 0
    assert snapshot["status"] == "idle"
    assert snapshot["exam_id"] == 1
    assert snapshot["classroom_name"] == "Test classroom 1"
    assert session.scalar(select(func.count(AttendanceRecord.id))) == 1


def test_demo_start_needs_no_exam_or_registration_and_preserves_normal_rules(api, session, monkeypatch):
    from app.demo import demo_exam, DEMO_CODE
    calls = []
    monkeypatch.setattr(control.jobs, "start", lambda kind, args: calls.append((kind, args)))
    before = session.scalar(select(func.count(Registration.id)))
    session.rollback()
    result = api.post("/control/camera/start", json={"demo_mode": True, "camera": 1, "source": "droidcam"})
    assert result.status_code == 200, result.text
    kind, args = calls[0]
    assert kind == "camera"
    assert args[args.index("--exam") + 1] == DEMO_CODE
    assert "--demo-mode" in args
    assert args[args.index("--camera-source") + 1] == "droidcam"
    assert session.scalar(select(func.count(Registration.id))) == before
    assert demo_exam(session).course_code == DEMO_CODE


def test_demo_readiness_requires_only_enrolled_faces(api, session):
    person = session.scalar(select(Student).where(Student.student_no == "UGS-26-020"))
    person.fees_cleared = False
    person.suspended = True
    session.add(FaceEmbedding(student_id=person.id, embedding=b"test", source_photo="capture:straight", det_score=1))
    session.commit()
    data = api.get("/control/readiness?demo=true").json()
    row = next(p for p in data if p["student_no"] == person.student_no)
    assert row["ready"] and not row["reasons"]
    assert person.suspended and not person.fees_cleared


def test_combined_demo_reset_repeats_round_and_preserves_real_records(api, session, monkeypatch, tmp_path):
    from app.attendance import mark_attendance
    from app.demo import demo_exam
    from app.live import LiveStore, LivePublisher
    store = LiveStore(tmp_path / "live.db")
    monkeypatch.setattr(control, "LiveStore", lambda: store)
    import app.main as main_module
    monkeypatch.setattr(main_module, "LiveStore", lambda: store)
    monkeypatch.setattr(control, "demo_reset_plans", {})
    exam = demo_exam(session, create=True)
    exam_id = exam.id
    person = session.scalar(select(Student).where(Student.student_no == "UGS-26-001"))
    session.add(FaceEmbedding(student_id=person.id, embedding=b"test", source_photo="capture:straight", det_score=1))
    session.commit()
    mark_attendance(session, exam_id=1, student_no=person.student_no)
    mark_attendance(session, exam_id=exam_id, student_no=person.student_no, demonstration=True)
    counts = [session.scalar(select(func.count(model.id))) for model in (Student, FaceEmbedding, Registration)]
    session.rollback()
    with LivePublisher(exam_id, store=store) as live:
        live.payload.update(demo_mode=True, demo_classroom=True)
        live.event("identified", student_no=person.student_no)
    assert api.get("/live/session").json()["present_count"] == 1
    response = api.post("/control/demo/reset/preview", json={})
    plan = response.json()
    assert plan["counts"] == {"attendance_records": 1, "activity_events": 2, "identified_count": 1}
    assert api.post("/control/demo/reset/confirm", json={"token": plan["token"], "confirmation": "no"}).status_code == 400
    result = api.post("/control/demo/reset/confirm", json={"token": plan["token"], "confirmation": "RESET"})
    assert result.status_code == 200, result.text
    assert store.read()["events"] == [] and store.read()["identified_count"] == 0
    assert store.read()["demo_mode"] and store.read()["exam_id"] == exam_id
    assert api.get("/live/session").json()["present_count"] == 0
    assert session.scalar(select(func.count(AttendanceRecord.id)).where(AttendanceRecord.exam_id == 1)) == 1
    assert session.scalar(select(func.count(AttendanceRecord.id)).where(AttendanceRecord.exam_id == exam_id)) == 0
    assert [session.scalar(select(func.count(model.id))) for model in (Student, FaceEmbedding, Registration)] == counts
    _, created = mark_attendance(session, exam_id=exam_id, student_no=person.student_no, demonstration=True)
    assert created
    assert api.post("/control/demo/reset/confirm", json={"token": plan["token"], "confirmation": "RESET"}).status_code == 409


def test_demo_reset_guards_changed_live_and_expiry_and_active_tasks(api, session, monkeypatch, tmp_path):
    from app.live import LiveStore, LivePublisher
    store = LiveStore(tmp_path / "live.db")
    monkeypatch.setattr(control, "LiveStore", lambda: store)
    monkeypatch.setattr(control, "demo_reset_plans", {})
    plan = api.post("/control/demo/reset/preview", json={}).json()
    with LivePublisher(1, store=store):
        assert api.post("/control/demo/reset/preview", json={}).status_code == 409
        assert api.post("/control/demo/reset/confirm", json={"token": plan["token"], "confirmation": "RESET"}).status_code == 409
    assert api.post("/control/demo/reset/confirm", json={"token": plan["token"], "confirmation": "RESET"}).status_code == 409
    plan = api.post("/control/demo/reset/preview", json={}).json()
    _, exam_id, snapshot = control.demo_reset_plans[plan["token"]]
    control.demo_reset_plans[plan["token"]] = (0, exam_id, snapshot)
    assert api.post("/control/demo/reset/confirm", json={"token": plan["token"], "confirmation": "RESET"}).status_code == 409


def test_local_enrollment_uses_selected_camera_model_and_explicit_replacement(api, session, monkeypatch):
    calls = []
    monkeypatch.setattr(control.sys, "platform", "win32")
    monkeypatch.setattr(control.jobs, "start", lambda kind, args: calls.append((kind, args)))
    payload = {"student_no": "VOL-NEW", "full_name": "New Volunteer", "camera": 1, "source": "droidcam", "capture_backend": "msmf"}
    response = api.post("/control/demo/enroll", json=payload)
    assert response.status_code == 200, response.text
    kind, args = calls[0]
    assert kind == "local_enroll" and args[0] == "app.vision.capture"
    assert "--student-no=VOL-NEW" in args and "--name=New Volunteer" in args
    assert args[args.index("--camera-source") + 1] == "droidcam"
    assert args[args.index("--capture-backend") + 1] == "msmf"
    assert args[args.index("--model") + 1] == control.ENROLL_MODEL
    assert "--stop-file" in args
    assert session.scalar(select(Student).where(Student.student_no == "VOL-NEW")) is None
    payload["student_no"] = "UGS-26-001"
    assert api.post("/control/demo/enroll", json=payload).status_code == 409
    assert api.post("/control/demo/enroll", json={**payload, "replace_existing": True}).status_code == 200
    assert api.post("/control/demo/enroll", json={**payload, "full_name": ""}).status_code == 422
    assert api.post("/control/demo/enroll", json={**payload, "student_no": "invalid\nID"}).status_code == 422


def test_local_enrollment_blocks_concurrent_camera_and_can_cancel(api, monkeypatch):
    control.jobs.kind = "local_enroll"
    control.jobs.process = SimpleNamespace(poll=lambda: None)
    assert api.post("/control/demo/enroll", json={"student_no": "NEW", "full_name": "New"}).status_code == 409
    assert api.post("/control/demo/reset/preview", json={}).status_code == 409
    assert api.post("/control/camera/stop", json={}).status_code == 200
    assert control.jobs.stop_path.read_text() == "stop"


def test_new_demo_routes_require_local_authorization(api):
    for path in ("enroll", "sync", "reset/preview", "reset/confirm"):
        assert api.post(f"/control/demo/{path}", json={}, headers={"X-Local-Control": "wrong"}).status_code == 403
