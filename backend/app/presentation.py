"""Display-only academic details for the current presentation; never eligibility rules.

Only rules explicitly agreed for this demo are applied: CSC department and year code
24 -> level 300. Other year codes are not extrapolated. Database values stay untouched.
"""
import re

DEPARTMENT_CSC = "Computer Science and Information Technology"
INDEX = re.compile(r"^[A-Z]+/([A-Z]+)/([0-9]{2})/[0-9]+$", re.IGNORECASE)


def academic_display(student_no: str, programme: str = "", level: int | None = None) -> dict:
    match = INDEX.fullmatch(student_no.strip())
    code, year = (match.group(1).upper(), match.group(2)) if match else (None, None)
    department = DEPARTMENT_CSC if code == "CSC" else None
    demo_level = year == "24"
    return {
        "department": department,
        "programme": programme or None,
        "level": 300 if demo_level else level,
        "index_programme_code": code,
        "index_year_code": year,
        "department_source": "demo_index_rule" if department else "not_supplied",
        "level_source": "demo_index_rule" if demo_level else "local_record",
        "is_demo_metadata": bool(department or demo_level),
    }


def camera_detail_lines(student_no: str, metadata: dict | None = None, demo_classroom: bool = False) -> list[str]:
    details = metadata if metadata is not None else academic_display(student_no)
    level = details.get("level")
    lines = [student_no + (f" | Level {level}" if level else "")]
    if details.get("department"):
        lines.append(details["department"])
    if demo_classroom:
        exam = demo_exam_for(student_no)
        lines.append(f"Demo exam: {exam['code']} - {exam['title']}")
    if details.get("is_demo_metadata"):
        lines.append("Academic details: presentation mapping")
    return lines


# Fictional presentation assignments only: never registration/eligibility/attendance keys.
DEMO_EXAMS = (
    ("CSC 301", "Software Engineering"),
    ("CSC 303", "Database Systems"),
    ("CSC 305", "Computer Networks"),
    ("CSC 307", "Operating Systems"),
    ("ITC 301", "Information Security"),
    ("MAT 301", "Discrete Mathematics"),
)


def demo_exam_for(student_no: str) -> dict:
    import hashlib
    # Stable randomized assignment: do not reshuffle a student's label on each scan/restart.
    digest = hashlib.sha256(("test-classroom-1:" + student_no.strip().upper()).encode()).digest()
    code, title = DEMO_EXAMS[int.from_bytes(digest[:8], "big") % len(DEMO_EXAMS)]
    return {"code": code, "title": title, "fictional": True}
