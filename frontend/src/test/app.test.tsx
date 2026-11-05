import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import App from "@/App"
import { FaceCapture } from "@/components/face-capture"
import type { Photos } from "@/lib/enrollment"

function mockCamera() {
  const stop = vi.fn()
  const stream = { getTracks: () => [{ stop }] } as unknown as MediaStream
  const getUserMedia = vi.fn().mockResolvedValue(stream)
  Object.defineProperty(navigator, "mediaDevices", { value: { getUserMedia }, configurable: true })
  Object.defineProperty(window, "isSecureContext", { value: true, configurable: true })
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined)
  return { getUserMedia, stop }
}

function mockCapture() {
  Object.defineProperty(HTMLVideoElement.prototype, "videoWidth", { value: 960, configurable: true })
  Object.defineProperty(HTMLVideoElement.prototype, "videoHeight", { value: 1280, configurable: true })
  const context = { translate: vi.fn(), scale: vi.fn(), drawImage: vi.fn() }
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context as unknown as CanvasRenderingContext2D)
  vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockReturnValue("data:image/jpeg;base64,test")
  return context
}

async function completeDetails(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByRole("textbox", { name: /full name/i }), "Ama Mensah")
  await user.type(screen.getByRole("textbox", { name: /index number/i }), "cs101-024")
  await user.click(screen.getByRole("checkbox"))
  await user.click(screen.getByRole("button", { name: /continue to photos/i }))
}

describe("enrollment app", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn())
  })

  it("shows the details form on first paint without a blocking overlay or camera request", () => {
    const { getUserMedia } = mockCamera()
    const { container } = render(<App />)
    expect(screen.getByRole("heading", { name: /register your face/i })).toBeInTheDocument()
    expect(screen.getByRole("textbox", { name: /full name/i })).toBeEnabled()
    expect(screen.getByRole("button", { name: /continue to photos/i })).toBeEnabled()
    expect(container.querySelector(".overlay")).not.toBeInTheDocument()
    expect(container.querySelector('[data-slot="spinner"]')).not.toBeInTheDocument()
    expect(getUserMedia).not.toHaveBeenCalled()
    expect(fetch).not.toHaveBeenCalled()
  })

  it("validates details and consent before opening the camera", async () => {
    const { getUserMedia } = mockCamera()
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole("button", { name: /continue to photos/i }))
    expect(screen.getByText("Enter your full name.")).toBeInTheDocument()
    expect(screen.getByText("Enter your index number.")).toBeInTheDocument()
    expect(screen.getByText(/consent is required/i)).toBeInTheDocument()
    expect(getUserMedia).not.toHaveBeenCalled()
    await completeDetails(user)
    expect(await screen.findByRole("heading", { name: /capture your photos/i })).toBeInTheDocument()
    await waitFor(() => expect(getUserMedia).toHaveBeenCalled())
  })

  it("captures three poses and reports direct enrollment only after the API succeeds", async () => {
    mockCamera()
    mockCapture()
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({
      ok: true, full_name: "Ama Mensah", student_no: "CS101-024", samples_saved: 3, registered_exam: "CS101",
    }), { status: 200, headers: { "Content-Type": "application/json" } }))
    const user = userEvent.setup()
    render(<App />)
    await completeDetails(user)
    await waitFor(() => expect(screen.getByRole("button", { name: /capture front photo/i })).toBeEnabled())
    await user.click(screen.getByRole("button", { name: /capture front photo/i }))
    await user.click(screen.getByRole("button", { name: /next: left/i }))
    await user.click(screen.getByRole("button", { name: /capture left photo/i }))
    await user.click(screen.getByRole("button", { name: /next: right/i }))
    await user.click(screen.getByRole("button", { name: /capture right photo/i }))
    await user.click(screen.getByRole("button", { name: /submit enrollment/i }))
    expect(await screen.findByRole("heading", { name: /you're enrolled/i })).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith("/enroll", expect.objectContaining({ method: "POST" }))
    const body = JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string)
    expect(body.student_no).toBe("CS101-024")
    expect(body.photos.map((photo: { step: string }) => photo.step)).toEqual(["straight", "left", "right"])
  })

  it("shows a recoverable camera permission error inside the camera card", async () => {
    const stop = vi.fn()
    const stream = { getTracks: () => [{ stop }] } as unknown as MediaStream
    const getUserMedia = vi.fn()
      .mockRejectedValueOnce(new DOMException("denied", "NotAllowedError"))
      .mockResolvedValue(stream)
    Object.defineProperty(navigator, "mediaDevices", { value: { getUserMedia }, configurable: true })
    Object.defineProperty(window, "isSecureContext", { value: true, configurable: true })
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined)
    const user = userEvent.setup()
    render(<FaceCapture photos={{ straight: null, left: null, right: null }} onChange={vi.fn()} onBack={vi.fn()} onSubmit={vi.fn()} submitting={false} submitError={null} />)
    expect(await screen.findByText("Camera unavailable")).toBeInTheDocument()
    expect(screen.getByText(/camera access was blocked/i)).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: /try again/i }))
    expect(await screen.findByText("Mirrored preview")).toBeInTheDocument()
  })

  it("stops camera tracks when the capture card unmounts", async () => {
    const { stop } = mockCamera()
    const { unmount } = render(<FaceCapture photos={{ straight: null, left: null, right: null }} onChange={vi.fn()} onBack={vi.fn()} onSubmit={vi.fn()} submitting={false} submitError={null} />)
    await waitFor(() => expect(screen.getByRole("button", { name: /capture front photo/i })).toBeEnabled())
    unmount()
    expect(stop).toHaveBeenCalled()
  })

  it("keeps loading inline and disables navigation while submitting", async () => {
    mockCamera()
    const photos: Photos = { straight: "data:image/jpeg;base64,a", left: "data:image/jpeg;base64,b", right: "data:image/jpeg;base64,c" }
    const { container } = render(
      <FaceCapture photos={photos} onChange={vi.fn()} onBack={vi.fn()} onSubmit={vi.fn()} submitting submitError={null} />,
    )
    await waitFor(() => expect(screen.getByRole("button", { name: /submitting/i })).toBeDisabled())
    expect(screen.getByRole("button", { name: /back to details/i })).toBeDisabled()
    expect(container.querySelector('[data-slot="spinner"]')).toBeInTheDocument()
    expect(container.querySelector(".overlay")).not.toBeInTheDocument()
  })
})
