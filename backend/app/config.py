import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
# Serve the compiled Vite app (frontend/dist), not the React source tree.
FRONTEND_DIR = Path(os.environ.get("FRONTEND_DIR", BASE_DIR.parent / "frontend" / "dist"))

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'exam_attendance.db'}")

# Web enrollment settings.
# The face model MUST match the one used by live attendance, or embeddings are incompatible.
ENROLL_MODEL = os.getenv("ENROLL_MODEL", "buffalo_l")
# If set, every web enrollment is also registered for this exam (e.g. "CS101"), so the
# group is ready for the attendance demo without a separate registration step.
ENROLL_DEFAULT_EXAM = os.getenv("ENROLL_DEFAULT_EXAM") or None
# Comma-separated list of allowed browser origins for the API ("*" allows any, fine for a demo).
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")

# Hybrid "Supabase inbox" sync (see app/sync.py and docs/HYBRID_SYNC.md).
# The phone app writes submissions to Supabase; this PC pulls and embeds them when online.
# SUPABASE_SERVICE_KEY is secret and stays on the PC — never put it in the frontend.
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
