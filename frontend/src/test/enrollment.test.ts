import { describe, expect, it, vi } from "vitest"
import { isSecretBrowserKey, type EnrollmentConfig } from "@/lib/config"
import { capturePhoto, emptyPhotos, submitEnrollment, type Photos } from "@/lib/enrollment"

const direct: EnrollmentConfig = { apiBase: "", exam: "CS101", supabaseUrl: "", supabaseAnonKey: "" }
const inbox: EnrollmentConfig = { apiBase: "", exam: "CS101", supabaseUrl: "https://example.supabase.co", supabaseAnonKey: "public-anon-key" }
const details = { fullName: " Ama Mensah ", studentNo: " cs101-024 " }
const photos: Photos = { straight: "data:image/jpeg;base64,a", left: "data:image/jpeg;base64,b", right: "data:image/jpeg;base64,c" }
const ok = () => new Response(null, { status: 201 })

describe("submitEnrollment", () => {
  it("posts the unchanged direct contract and reports enrolled only on success", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      student_no: "CS101-024", full_name: "Ama Mensah", samples_saved: 3, registered_exam: "CS101",
    }), { status: 200 }))
    const receipt = await submitEnrollment(details, photos, direct, fetchImpl)
    expect(fetchImpl).toHaveBeenCalledWith("/enroll", expect.objectContaining({ method: "POST" }))
    const init = fetchImpl.mock.calls[0][1]!
    expect(JSON.parse(init.body as string)).toEqual({
      full_name: "Ama Mensah", student_no: "CS101-024", exam: "CS101",
      photos: [{ step: "straight", image: photos.straight }, { step: "left", image: photos.left }, { step: "right", image: photos.right }],
    })
    expect(receipt).toMatchObject({ status: "enrolled", studentNo: "CS101-024", photoCount: 3, exam: "CS101" })
  })

  it("inserts into the Supabase inbox and honestly reports queued, not enrolled", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(ok())
    const receipt = await submitEnrollment(details, photos, inbox, fetchImpl)
    expect(fetchImpl).toHaveBeenCalledWith("https://example.supabase.co/rest/v1/enroll_submissions", expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({ apikey: "public-anon-key", Authorization: "Bearer public-anon-key", Prefer: "return=minimal" }),
    }))
    expect(receipt.status).toBe("queued")
  })

  it("rejects incomplete inbox configuration and secret browser keys before sending photos", async () => {
    const fetchImpl = vi.fn<typeof fetch>()
    await expect(submitEnrollment(details, photos, { ...inbox, supabaseAnonKey: "" }, fetchImpl)).rejects.toThrow(/partly configured/i)
    await expect(submitEnrollment(details, photos, { ...inbox, supabaseAnonKey: "sb_secret_do-not-use" }, fetchImpl)).rejects.toThrow(/secret key/i)
    expect(fetchImpl).not.toHaveBeenCalled()
    expect(isSecretBrowserKey(`x.${btoa(JSON.stringify({ role: "service_role" }))}.y`)).toBe(true)
    expect(isSecretBrowserKey("public-anon-key")).toBe(false)
  })

  it("requires all three photos", async () => {
    await expect(submitEnrollment(details, { ...emptyPhotos(), straight: "x" }, direct, vi.fn())).rejects.toThrow(/left photo/i)
  })

  it("explains a missing static-host enrollment endpoint instead of spinning forever", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response("<html>Not found</html>", { status: 404 }))
    await expect(submitEnrollment(details, photos, direct, fetchImpl)).rejects.toThrow(/Netlify.*Supabase inbox/i)
  })

  it("surfaces backend face-quality problems", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({ detail: { problems: ["No face in left photo", "Too dark"] } }), { status: 422 }))
    await expect(submitEnrollment(details, photos, direct, fetchImpl)).rejects.toThrow("No face in left photo Too dark")
  })

  it("bounds requests with a timeout and gives a recoverable network error", async () => {
    vi.useFakeTimers()
    const hanging: typeof fetch = (_url, init) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")))
    })
    const pending = submitEnrollment(details, photos, direct, hanging)
    const assertion = expect(pending).rejects.toThrow(/timed out/i)
    await vi.advanceTimersByTimeAsync(45_000)
    await assertion
    vi.useRealTimers()
    await expect(submitEnrollment(details, photos, direct, vi.fn<typeof fetch>().mockRejectedValue(new TypeError("Failed to fetch")))).rejects.toThrow(/could not reach/i)
  })
})

describe("capturePhoto", () => {
  it("mirrors the frame and limits the longest edge to 720px", () => {
    const context = { translate: vi.fn(), scale: vi.fn(), drawImage: vi.fn() }
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context as unknown as CanvasRenderingContext2D)
    vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockReturnValue("data:image/jpeg;base64,mirrored")
    const video = document.createElement("video")
    Object.defineProperty(video, "videoWidth", { value: 960 })
    Object.defineProperty(video, "videoHeight", { value: 1280 })
    expect(capturePhoto(video)).toBe("data:image/jpeg;base64,mirrored")
    expect(context.translate).toHaveBeenCalledWith(540, 0)
    expect(context.scale).toHaveBeenCalledWith(-1, 1)
    expect(context.drawImage).toHaveBeenCalledWith(video, 0, 0, 540, 720)
  })
})
