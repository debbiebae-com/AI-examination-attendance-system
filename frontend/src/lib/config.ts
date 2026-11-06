type LegacyConfig = {
  API_BASE?: string
  EXAM?: string
  SUPABASE_URL?: string
  SUPABASE_ANON_KEY?: string
}

declare global {
  interface Window {
    ENROLL_CONFIG?: LegacyConfig
  }
}

export type EnrollmentConfig = {
  apiBase: string
  exam: string
  supabaseUrl: string
  supabaseAnonKey: string
}

const legacy = typeof window === "undefined" ? {} : (window.ENROLL_CONFIG ?? {})
const choose = (value: string | undefined, fallback: string | undefined) =>
  (value || fallback || "").trim()

// Build-time variables are the recommended Netlify configuration. The optional public/config.js
// remains supported for existing deployments and is copied unchanged into the build.
export const enrollmentConfig: EnrollmentConfig = {
  apiBase: choose(import.meta.env.VITE_API_BASE, legacy.API_BASE).replace(/\/+$/, ""),
  exam: choose(import.meta.env.VITE_ENROLL_EXAM, legacy.EXAM),
  supabaseUrl: choose(import.meta.env.VITE_SUPABASE_URL, legacy.SUPABASE_URL).replace(/\/+$/, ""),
  supabaseAnonKey: choose(import.meta.env.VITE_SUPABASE_ANON_KEY, legacy.SUPABASE_ANON_KEY),
}

export function usesInbox(config = enrollmentConfig) {
  return Boolean(config.supabaseUrl || config.supabaseAnonKey)
}

export function isSecretBrowserKey(key: string) {
  if (key.startsWith("sb_secret_")) return true
  const parts = key.split(".")
  if (parts.length !== 3) return false
  try {
    const payload = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")))
    return payload.role === "service_role"
  } catch {
    return false
  }
}
