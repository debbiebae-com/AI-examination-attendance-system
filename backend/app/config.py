import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
# The student-facing web app lives at the repository root, next to backend/.
FRONTEND_DIR = BASE_DIR.parent / "frontend"

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'exam_attendance.db'}")

# Web enrollment settings.
# The face model MUST match the one used by live attendance, or embeddings are incompatible.
ENROLL_MODEL = os.getenv("ENROLL_MODEL", "buffalo_l")
# If set, every web enrollment is also registered for this exam (e.g. "CS101"), so the
# group is ready for the attendance demo without a separate registration step.
ENROLL_DEFAULT_EXAM = os.getenv("ENROLL_DEFAULT_EXAM") or None
# Comma-separated list of allowed browser origins for the API ("*" allows any, fine for a demo).
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
