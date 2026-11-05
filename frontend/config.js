// Frontend configuration.
//
// Two modes:
//
// 1) DIRECT mode (default): the page POSTs to the FastAPI backend, which computes the face
//    embeddings immediately. Use this when the backend is running (your PC, or a hosted server).
//      API_BASE: "" for same-origin (FastAPI serves this page at /app), or the backend URL.
//
// 2) SUPABASE INBOX mode (hybrid): set SUPABASE_URL + SUPABASE_ANON_KEY. The page stores each
//    submission (name, index number, 3 photos) in Supabase so members can submit ANYTIME, even
//    when the organizer's PC is off. The organizer later runs `python -m app.sync` on their PC
//    to compute the embeddings with the full-accuracy model. No face model runs in the cloud.
//    See docs/HYBRID_SYNC.md. The anon key is public-safe (insert-only via Row-Level Security).
window.ENROLL_CONFIG = {
  API_BASE: "",
  EXAM: "",

  // Hybrid inbox mode — fill these in (from Supabase → Project Settings → API):
  SUPABASE_URL: "",        // e.g. "https://abcdefgh.supabase.co"
  SUPABASE_ANON_KEY: "",   // the public "anon" key (NOT the service_role key)
};
