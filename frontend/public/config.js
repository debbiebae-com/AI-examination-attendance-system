// Optional runtime overrides, copied unchanged to dist/config.js.
// Prefer VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY / VITE_ENROLL_EXAM in Netlify.
// Values here support older deployments; non-empty VITE_* variables take precedence.
// NEVER put a service_role or sb_secret_ key in this public file.
window.ENROLL_CONFIG = {
  API_BASE: "",
  EXAM: "",
  SUPABASE_URL: "",
  SUPABASE_ANON_KEY: "",
};
