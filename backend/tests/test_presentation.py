import pytest
from app.presentation import academic_display, camera_detail_lines


def test_agreed_csc_and_year_24_display_mapping():
    result=academic_display("PS/CSC/24/0016", "Volunteer (web)", 100)
    assert result["department"] == "Computer Science and Information Technology"
    assert result["level"] == 300
    assert result["level_source"] == "demo_index_rule"
    assert result["is_demo_metadata"]
    assert "PS/CSC/24/0016 | Level 300" in camera_detail_lines("PS/CSC/24/0016", result)


def test_rules_are_independent_and_other_years_not_extrapolated():
    assert academic_display("PS/CSC/23/0042", level=200)["level"] == 200
    assert academic_display("PS/ITC/24/0016", level=100)["level"] == 300
    assert academic_display("PS/ITC/24/0016")["department"] is None
    assert academic_display("VOL-002", level=100)["level"] == 100
    assert not academic_display("VOL-002", level=100)["is_demo_metadata"]


def test_case_whitespace_and_structural_validation():
    assert academic_display(" ps/csc/24/0016 ")["level"] == 300
    for number in ["NOTCSC24", "PS/CSC/240/0016", "PS/CSC/24", "PS/CSC/24/abc"]:
        assert academic_display(number)["department"] is None
        assert academic_display(number)["level"] is None


def test_students_api_adds_display_values_without_updating_database(session):
    from app.main import list_students
    from app.models import Student
    student=Student(student_no="PS/CSC/24/0016",full_name="Volunteer",programme="Local",level=100,fees_cleared=False,suspended=True)
    session.add(student);session.commit()
    data=next(row for row in list_students(session) if row["student_no"] == student.student_no)
    assert data["level"] == 100
    assert data["presentation"]["level"] == 300
    session.refresh(student)
    assert student.level == 100 and not student.fees_cleared and student.suspended


def test_camera_overlay_fits_long_lines_and_only_decorates_confirmed_faces(monkeypatch):
    pytest.importorskip("cv2")
    pytest.importorskip("supervision")
    import numpy as np
    from app.vision import attend
    from app.vision.attendance_flow import FaceTracker, AttendanceDecider
    from app.vision.embedder import DetectedFace
    tracker=FaceTracker();tid=tracker.update([(100,100,200,200)])[0]
    decider=AttendanceDecider(tracker,confirm_frames=1)
    calls=[]
    monkeypatch.setattr(attend,"draw_face_card",lambda image,lines,*args:calls.append(lines))
    faces=[DetectedFace(bbox=(100,100,200,200),score=0.9)]
    image=np.zeros((240,320,3),dtype=np.uint8)
    attend.draw(image,faces,[tid],tracker,decider,{},[])
    assert not any("Level 300" in line for line in calls[-1])
    decider.observe(tid,is_live=None,student_no="PS/CSC/24/0016")
    attend.draw(image,faces,[tid],tracker,decider,{},[])
    assert any("Level 300" in line for line in calls[-1])
    for line in attend.wrap_overlay("PS/CSC/24/0016 Computer Science and Information Technology",100):
        assert attend.cv2.getTextSize(line,attend.FONT,0.43,1)[0][0] <= 100
