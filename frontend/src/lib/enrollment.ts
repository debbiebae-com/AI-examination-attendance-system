import { isSecretBrowserKey, usesInbox, type EnrollmentConfig } from "@/lib/config"

// Guided capture mirrors the desktop flow: one prompt per pose, several frames collected
// automatically while the person follows the instruction. The PC sync does the face check.
export const FRAMES_PER_POSE = 3
export const COUNTDOWN_SECONDS = 3
export const CAPTURE_INTERVAL_MS = 800
export const POSE_PAUSE_MS = 1200

export const POSES = [
  { step: "straight", label: "Front", title: "Look straight at the camera", hint: "Face the camera at eye level and hold still." },
  { step: "left", label: "Left", title: "Slowly turn your head to your LEFT", hint: "Turn toward your own left, not the screen's left." },
  { step: "right", label: "Right", title: "Slowly turn your head to your RIGHT", hint: "Turn toward your own right. Keep your face visible." },
] as const

export type PoseStep = (typeof POSES)[number]["step"]
export type Photos = Record<PoseStep, string[]>
export type StudentDetails = { fullName: string; studentNo: string }
export type Receipt = StudentDetails & {
  photoCount: number
  exam: string | null
  status: "queued" | "enrolled"
}

export const emptyPhotos = (): Photos => ({ straight: [], left: [], right: [] })
export const copyPhotos = (photos: Photos): Photos => ({
  straight: [...photos.straight],
  left: [...photos.left],
  right: [...photos.right],
})
export const totalFrames = (photos: Photos) => POSES.reduce((sum, { step }) => sum + photos[step].length, 0)
export const captureComplete = (photos: Photos) => POSES.every(({ step }) => photos[step].length >= FRAMES_PER_POSE)

export function capturePhoto(video: HTMLVideoElement, maxDimension = 720) {
  if (!video.videoWidth || !video.videoHeight) {
    throw new Error("The camera preview is not ready yet. Wait a moment and try again.")
  }
  const scale = Math.min(1, maxDimension / Math.max(video.videoWidth, video.videoHeight))
  const canvas = document.createElement("canvas")
  canvas.width = Math.round(video.videoWidth * scale)
  canvas.height = Math.round(video.videoHeight * scale)
  const context = canvas.getContext("2d")
  if (!context) throw new Error("This browser could not capture the frame. Try a current browser.")
  // Match the mirrored orientation used by desktop capture and live attendance.
  context.translate(canvas.width, 0)
  context.scale(-1, 1)
  context.drawImage(video, 0, 0, canvas.width, canvas.height)
  return canvas.toDataURL("image/jpeg", 0.9)
}

async function responseError(response: Response) {
  if (response.status === 404) {
    return "The enrollment service was not found. On Netlify, the organizer needs to connect the Supabase inbox in the site's environment variables."
  }
  try {
    const data = await response.json()
    const detail = data.detail ?? data
    if (Array.isArray(detail?.problems)) return detail.problems.join(" ")
    const message = typeof detail === "string" ? detail : detail?.message || data.message || data.msg
    if (message && !String(message).trimStart().startsWith("<")) return String(message).slice(0, 400)
  } catch {
    // Static hosts may return an HTML error page instead of JSON.
  }
  if (response.status === 401 || response.status === 403) {
    return "The inbox rejected this submission. Ask the organizer to check the Supabase public key and insert policy."
  }
  return `Submission failed (${response.status}). Check your connection and try again.`
}

export async function submitEnrollment(
  details: StudentDetails,
  photos: Photos,
  config: EnrollmentConfig,
  fetchImpl: typeof fetch = (...args) => fetch(...args),
): Promise<Receipt> {
  const inbox = usesInbox(config)
  if (inbox && (!config.supabaseUrl || !config.supabaseAnonKey)) {
    throw new Error("The Supabase inbox is only partly configured. Ask the organizer to set both the project URL and public key.")
  }
  if (inbox && isSecretBrowserKey(config.supabaseAnonKey)) {
    throw new Error("A secret key was supplied to the browser. Ask the organizer to replace it with the public anon or publishable key.")
  }
  const payloadPhotos = POSES.flatMap(({ step }) => {
    const frames = photos[step]
    if (frames.length === 0) throw new Error(`Complete the ${step} capture before submitting.`)
    return frames.map((image) => ({ step, image }))
  })
  const payload = {
    full_name: details.fullName.trim(),
    student_no: details.studentNo.trim().toUpperCase(),
    photos: payloadPhotos,
    ...(config.exam ? { exam: config.exam } : {}),
  }
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 45_000)
  let response: Response
  try {
    const url = inbox ? `${config.supabaseUrl}/rest/v1/enroll_submissions` : `${config.apiBase}/enroll`
    response = await fetchImpl(url, {
      method: "POST",
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(inbox
          ? { apikey: config.supabaseAnonKey, Authorization: `Bearer ${config.supabaseAnonKey}`, Prefer: "return=minimal" }
          : {}),
      },
      body: JSON.stringify(payload),
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("The request timed out. Check your connection and confirm with the organizer before submitting again.")
    }
    throw new Error("Could not reach the enrollment service. Check your connection and try again.")
  } finally {
    window.clearTimeout(timeout)
  }
  if (!response.ok) throw new Error(await responseError(response))
  const base = {
    fullName: payload.full_name,
    studentNo: payload.student_no,
    photoCount: payloadPhotos.length,
    exam: config.exam || null,
  }
  if (inbox) return { ...base, status: "queued" }
  const data = await response.json().catch(() => ({}))
  return {
    ...base,
    fullName: data.full_name || base.fullName,
    studentNo: data.student_no || base.studentNo,
    photoCount: typeof data.samples_saved === "number" ? data.samples_saved : base.photoCount,
    exam: data.registered_exam || base.exam,
    status: "enrolled",
  }
}
