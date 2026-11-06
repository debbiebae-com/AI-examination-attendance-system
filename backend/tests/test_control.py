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
