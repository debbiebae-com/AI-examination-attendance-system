import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import App from "@/App"
import { FaceCapture } from "@/components/face-capture"
import { emptyPhotos, type Photos } from "@/lib/enrollment"

const poseMock = vi.hoisted(() => ({ count:0, faceCount:1, frontOnly:false, wrongTurn:false, failInit:false, closes:0 }))
vi.mock("@/lib/pose-detector", () => ({
  PoseDetector: class {
    async init() { if(poseMock.failInit) throw new Error("Pose model unavailable") }
    async sample() {
      const stage = Math.floor(poseMock.count++ / 5)
      const yaw = poseMock.frontOnly ? 0 : stage === 0 ? 0 : stage === 1 ? (poseMock.wrongTurn ? -25 : 25) : -25
      return {observation:{faces:poseMock.faceCount,yaw,pitch:0,roll:0,width:0.4,height:0.5,cx:0.5,cy:0.5},photo:()=>"data:image/jpeg;base64,test"}
    }
    close() {poseMock.closes++}
  },
}))
vi.mock("@/lib/pose", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/pose")>(), HOLD_MS:0, SAMPLE_INTERVAL_MS:1,
  PoseGate: class {
    count=0
    observe(valid:boolean) {this.count=valid?this.count+1:0;return {ready:this.count>=3,held:0}}
  },
}))

// Accelerate the UI harness; pose timing/stability has its own unmocked unit tests.
vi.mock("@/lib/enrollment", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/enrollment")>()
  return { ...actual, CAPTURE_INTERVAL_MS: 0, POSE_PAUSE_MS: 1 }
})

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

function fullPhotos(): Photos {
  return {
    straight: ["data:image/jpeg;base64,a", "data:image/jpeg;base64,b", "data:image/jpeg;base64,c"],
    left: ["data:image/jpeg;base64,d", "data:image/jpeg;base64,e", "data:image/jpeg;base64,f"],
    right: ["data:image/jpeg;base64,g", "data:image/jpeg;base64,h", "data:image/jpeg;base64,i"],
  }
}

async function completeDetails(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByRole("textbox", { name: /full name/i }), "Ama Mensah")
  await user.type(screen.getByRole("textbox", { name: /index number/i }), "ps/csc/24/0016")
  await user.click(screen.getByRole("checkbox"))
  await user.click(screen.getByRole("button", { name: /continue to capture/i }))
}

describe("enrollment app", () => {
  beforeEach(() => {
    Object.assign(poseMock,{count:0,faceCount:1,frontOnly:false,wrongTurn:false,failInit:false,closes:0})
    vi.stubGlobal("fetch", vi.fn())
  })

  it("shows the details form on first paint without a blocking overlay or camera request", () => {
    const { getUserMedia } = mockCamera()
    const { container } = render(<App />)
    expect(screen.getByRole("heading", { name: /register your face/i })).toBeInTheDocument()
    expect(screen.getByRole("textbox", { name: /full name/i })).toBeEnabled()
    expect(screen.getByRole("button", { name: /continue to capture/i })).toBeEnabled()
    expect(screen.getByPlaceholderText("e.g. PS/CSC/24/0016")).toBeInTheDocument()
    expect(container.querySelector(".overlay")).not.toBeInTheDocument()
    expect(container.querySelector('[data-slot="spinner"]')).not.toBeInTheDocument()
    expect(getUserMedia).not.toHaveBeenCalled()
    expect(fetch).not.toHaveBeenCalled()
  })

  it("validates details and consent before opening the camera", async () => {
    const { getUserMedia } = mockCamera()
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole("button", { name: /continue to capture/i }))
    expect(screen.getByText("Enter your full name.")).toBeInTheDocument()
    expect(screen.getByText("Enter your index number.")).toBeInTheDocument()
    expect(screen.getByText(/consent is required/i)).toBeInTheDocument()
    expect(getUserMedia).not.toHaveBeenCalled()
    await completeDetails(user)
    expect(await screen.findByRole("heading", { name: /guided face capture/i })).toBeInTheDocument()
    await waitFor(() => expect(getUserMedia).toHaveBeenCalled())
  })

  it("runs a guided video capture with no photo button and submits long index numbers", async () => {
    mockCamera()
    mockCapture()
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({
      ok: true, full_name: "Ama Mensah", student_no: "PS/CSC/24/0016", samples_saved: 9, registered_exam: "CS101",
    }), { status: 200, headers: { "Content-Type": "application/json" } }))
    const user = userEvent.setup()
    render(<App />)
    await completeDetails(user)
    const start = await screen.findByRole("button", { name: /start guided capture/i })
    await waitFor(() => expect(start).toBeEnabled())
    expect(screen.queryByRole("button", { name: /capture front photo/i })).not.toBeInTheDocument()
    expect(screen.getByLabelText(/mirrored live camera preview/i)).toBeInTheDocument()
    await user.click(start)
    await user.click(await screen.findByRole("button", { name: /submit enrollment/i }))
    expect(await screen.findByRole("heading", { name: /you're enrolled/i })).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith("/enroll", expect.objectContaining({ method: "POST" }))
    const body = JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string)
    expect(body.student_no).toBe("PS/CSC/24/0016")
    expect(body.photos).toHaveLength(9)
    expect(body.photos.map((photo: { step: string }) => photo.step)).toEqual([
      "straight", "straight", "straight", "left", "left", "left", "right", "right", "right",
    ])
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
    render(<FaceCapture photos={emptyPhotos()} onChange={vi.fn()} onBack={vi.fn()} onSubmit={vi.fn()} submitting={false} submitError={null} />)
    expect(await screen.findByText("Camera unavailable")).toBeInTheDocument()
    expect(screen.getByText(/camera access was blocked/i)).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: /try again/i }))
    await waitFor(() => expect(screen.getByRole("button", { name: /start guided capture/i })).toBeEnabled())
  })

  it("stops camera tracks when the capture card unmounts", async () => {
    const { stop } = mockCamera()
    const { unmount } = render(<FaceCapture photos={emptyPhotos()} onChange={vi.fn()} onBack={vi.fn()} onSubmit={vi.fn()} submitting={false} submitError={null} />)
    await waitFor(() => expect(screen.getByRole("button", { name: /start guided capture/i })).toBeEnabled())
    unmount()
    expect(stop).toHaveBeenCalled()
    expect(poseMock.closes).toBeGreaterThan(0)
  })

  it("keeps loading inline and disables navigation while submitting", async () => {
    mockCamera()
    const { container } = render(
      <FaceCapture photos={fullPhotos()} onChange={vi.fn()} onBack={vi.fn()} onSubmit={vi.fn()} submitting submitError={null} />,
    )
    await waitFor(() => expect(screen.getByRole("button", { name: /submitting/i })).toBeDisabled())
    expect(screen.getByRole("button", { name: /back to details/i })).toBeDisabled()
    expect(container.querySelector('[data-slot="spinner"]')).toBeInTheDocument()
    expect(container.querySelector(".overlay")).not.toBeInTheDocument()
  })
})


describe("pose-gated capture", () => {
  beforeEach(() => Object.assign(poseMock,{count:0,faceCount:1,frontOnly:false,wrongTurn:false,failInit:false,closes:0}))
  it("never advances the left pose if the person stays facing forward", async () => {
    mockCamera(); poseMock.frontOnly=true
    const user=userEvent.setup()
    render(<FaceCapture photos={emptyPhotos()} onChange={vi.fn()} onBack={vi.fn()} onSubmit={vi.fn()} submitting={false} submitError={null}/> )
    const start=screen.getByRole("button",{name:/start guided capture/i})
    await waitFor(()=>expect(start).toBeEnabled());await user.click(start)
    await waitFor(()=>expect(screen.getByText(/turn a little more to your LEFT/i)).toBeInTheDocument())
    expect(screen.getByLabelText("Left: 0 of 3 frames")).toBeInTheDocument()
    expect(screen.queryByRole("button",{name:/submit enrollment/i})).not.toBeInTheDocument()
  })
  it("reports a wrong-way turn without collecting left frames",async()=>{
    mockCamera();poseMock.wrongTurn=true
    const user=userEvent.setup()
    render(<FaceCapture photos={emptyPhotos()} onChange={vi.fn()} onBack={vi.fn()} onSubmit={vi.fn()} submitting={false} submitError={null}/> )
    const start=screen.getByRole("button",{name:/start guided capture/i})
    await waitFor(()=>expect(start).toBeEnabled());await user.click(start)
    expect(await screen.findByText(/That's your RIGHT/)).toBeInTheDocument()
    expect(screen.getByLabelText("Left: 0 of 3 frames")).toBeInTheDocument()
  })
  it("fails closed if the pose model cannot load, then permits explicit retry",async()=>{
    mockCamera();poseMock.failInit=true
    const user=userEvent.setup()
    render(<FaceCapture photos={emptyPhotos()} onChange={vi.fn()} onBack={vi.fn()} onSubmit={vi.fn()} submitting={false} submitError={null}/> )
    expect(await screen.findByText("Pose model unavailable")).toBeInTheDocument()
    expect(screen.getByRole("button",{name:/start guided capture/i})).toBeDisabled()
    poseMock.failInit=false
    await user.click(screen.getByRole("button",{name:/retry pose checker/i}))
    await waitFor(()=>expect(screen.getByRole("button",{name:/start guided capture/i})).toBeEnabled())
  })
})

it.each([0,2])("does not collect frames when the detector sees %s faces",async(faces)=>{
  Object.assign(poseMock,{count:0,faceCount:faces,frontOnly:false,wrongTurn:false,failInit:false,closes:0})
  mockCamera()
  const user=userEvent.setup()
  const changed=vi.fn()
  render(<FaceCapture photos={emptyPhotos()} onChange={changed} onBack={vi.fn()} onSubmit={vi.fn()} submitting={false} submitError={null}/> )
  const start=screen.getByRole("button",{name:/start guided capture/i})
  await waitFor(()=>expect(start).toBeEnabled());await user.click(start)
  await screen.findByText(faces===0 ? /No face found/ : /Only one person should/)
  expect(screen.getByLabelText("Front: 0 of 3 frames")).toBeInTheDocument()
  expect(changed).toHaveBeenCalledTimes(1) // initial clear only
})
