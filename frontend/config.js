// Frontend configuration.
//
// API_BASE: where the FastAPI backend lives.
//   "" (empty)  -> same origin. Use this when FastAPI itself serves this page at /app
//                  (the simplest single-server deployment).
//   "https://your-backend.example.com" -> set this when the frontend is hosted
//                  separately (e.g. Netlify/Vercel) from the backend.
//
// EXAM: optional course code to auto-register each enrollee for (e.g. "CS101").
//   Leave as "" to let the backend decide (ENROLL_DEFAULT_EXAM env var), or to register
//   later with:  uv run python -m app.register --exam CS101 --student-no ...
window.ENROLL_CONFIG = {
  API_BASE: "",
  EXAM: "",
};
