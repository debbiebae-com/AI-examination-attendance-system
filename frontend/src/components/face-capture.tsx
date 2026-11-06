import { useEffect, useRef, useState } from "react"
import { ArrowLeft, Camera, Check, CircleAlert, Play, RefreshCw, Send, Video, VideoOff } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Spinner } from "@/components/ui/spinner"
import { useCamera } from "@/hooks/use-camera"
import {
  CAPTURE_INTERVAL_MS,
  FRAMES_PER_POSE,
  POSE_PAUSE_MS,
  POSES,
  captureComplete,
  copyPhotos,
  emptyPhotos,
  totalFrames,
  type Photos,
} from "@/lib/enrollment"
import { PoseDetector } from "@/lib/pose-detector"
import { checkPose, PoseGate, HOLD_MS, SAMPLE_INTERVAL_MS, POSE_TIMEOUT_MS } from "@/lib/pose"
import { cn } from "@/lib/utils"

type Props = {
  photos: Photos
  onChange: (photos: Photos) => void
  onBack: () => void
  onSubmit: () => void
  submitting: boolean
  submitError: string | null
}

type Phase = "ready" | "waiting" | "countdown" | "collecting" | "transition" | "complete" | "error"

const sleep = (ms: number) => new Promise<void>((resolve) => window.setTimeout(resolve, ms))

export function FaceCapture({ photos, onChange, onBack, onSubmit, submitting, submitError }: Props) {
  const { videoRef, status, error, retry } = useCamera()
  const [phase, setPhase] = useState<Phase>(() => (captureComplete(photos) ? "complete" : "ready"))
  const [activeIndex, setActiveIndex] = useState(0)
  const [countdown, setCountdown] = useState(1)
  const [captureError, setCaptureError] = useState<string | null>(null)
  const [poseStatus, setPoseStatus] = useState<"loading" | "ready" | "error">("loading")
  const [poseError, setPoseError] = useState<string | null>(null)
  const [poseRetry, setPoseRetry] = useState(0)
  const [guidance, setGuidance] = useState("Head position is checked before every saved frame.")
  const detectorRef = useRef<PoseDetector | null>(null)
  const runId = useRef(0)
  const collected = useRef<Photos>(copyPhotos(photos))

  useEffect(() => () => { runId.current += 1 }, [])

  useEffect(() => {
    if (status !== "ready") return
    let disposed = false
    let detector: PoseDetector | null = null
    setPoseStatus("loading")
    setPoseError(null)
    try {
      detector = new PoseDetector()
      detectorRef.current = detector
      void detector.init().then(() => {
        if (!disposed) setPoseStatus("ready")
      }).catch(cause => {
        if (!disposed) {
          setPoseStatus("error")
          setPoseError(cause instanceof Error ? cause.message : "Head pose checker failed to load.")
        }
      })
    } catch (cause) {
      setPoseStatus("error")
      setPoseError(cause instanceof Error ? cause.message : "Head pose checking is unavailable.")
    }
    return () => {
      disposed = true
      runId.current += 1
      detector?.close()
      detectorRef.current = null
    }
  }, [status, poseRetry])

  // If the camera drops mid-capture, stop the sequence instead of collecting stale frames.
  useEffect(() => {
    if (status === "error" && (phase === "waiting" || phase === "countdown" || phase === "collecting" || phase === "transition")) {
      runId.current += 1
      setPhase("ready")
    }
  }, [status, phase])

  async function start() {
    const token = ++runId.current
    const cancelled = () => runId.current !== token
    collected.current = emptyPhotos()
    onChange(emptyPhotos())
    setCaptureError(null)
    setActiveIndex(0)
    try {
      for (let i = 0; i < POSES.length; i++) {
        setActiveIndex(i)
        setPhase("waiting")
        const detector = detectorRef.current
        if (!detector || poseStatus !== "ready") throw new Error("Wait for the head pose checker to finish loading.")
        const gate = new PoseGate()
        const deadline = performance.now() + POSE_TIMEOUT_MS
        let lastCapture = -Infinity
        const step = POSES[i].step
        while (collected.current[step].length < FRAMES_PER_POSE) {
          await sleep(SAMPLE_INTERVAL_MS)
          if (cancelled()) return
          const began = performance.now()
          if (began > deadline) throw new Error(`Could not verify the ${step} pose. Use good light, keep one face visible and follow the feedback. Restart to try again.`)
          if (document.hidden) {
            gate.observe(false, began)
            setGuidance("Return to this tab to continue capture.")
            continue
          }
          const video = videoRef.current
          if (!video) throw new Error("The camera preview disappeared. Restart the capture.")
          const sample = await detector.sample(video)
          if (cancelled()) return
          const now = performance.now()
          if (!sample || now - began > 1500) {
            gate.observe(false, now)
            setPhase("waiting")
            setGuidance("Waiting for a fresh camera frame. Keep this tab open.")
            continue
          }
          const check = checkPose(sample.observation, step)
          const hold = gate.observe(check.valid, now)
          setGuidance(check.message)
          setCountdown(Math.max(1, Math.ceil((HOLD_MS - hold.held) / 1000)))
          setPhase(!check.valid ? "waiting" : hold.ready ? "collecting" : "countdown")
          if (!hold.ready || now - lastCapture < CAPTURE_INTERVAL_MS) continue
          const image = sample.photo()
          collected.current = { ...collected.current, [step]: [...collected.current[step], image] }
          onChange(copyPhotos(collected.current))
          lastCapture = now
        }
        if (i < POSES.length - 1) {
          setPhase("transition")
          await sleep(POSE_PAUSE_MS)
          if (cancelled()) return
        }
      }
      if (!cancelled()) setPhase("complete")
    } catch (cause) {
      if (cancelled()) return
      setCaptureError(cause instanceof Error ? cause.message : "Could not collect frames. Restart the capture.")
      if (cause instanceof Error && cause.name === "PoseDetectorError") {
        detectorRef.current?.close()
        setPoseStatus("error")
        setPoseError(cause.message)
      }
      setPhase("error")
    }
  }

  const pose = POSES[activeIndex]
  const nextPose = POSES[activeIndex + 1]
  const running = phase === "waiting" || phase === "countdown" || phase === "collecting" || phase === "transition"
  const frames = totalFrames(photos)
  const progress = Math.round((frames / (FRAMES_PER_POSE * POSES.length)) * 100)

  const prompt =
    phase === "complete" ? "Capture complete" :
    phase === "transition" && nextPose ? `Good. Next: ${nextPose.title.toLowerCase()}` :
    pose.title

  return (
    <Card aria-busy={submitting}>
      <CardHeader>
        <CardTitle className="text-xl">Guided face capture</CardTitle>
        <CardDescription>
          Follow the prompts while the camera stays live. Frames are collected only after your head position is verified — no photo button.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid grid-cols-3 gap-3" aria-label="Capture checklist">
          {POSES.map(({ step, label }, index) => {
            const count = photos[step].length
            const done = count >= FRAMES_PER_POSE
            const last = count > 0 ? photos[step][count - 1] : null
            return (
              <div
                key={step}
                className={cn(
                  "relative flex aspect-[4/3] items-center justify-center overflow-hidden rounded-lg border bg-muted",
                  running && index === activeIndex && "ring-2 ring-primary ring-offset-2 ring-offset-card",
                )}
                aria-label={`${label}: ${count} of ${FRAMES_PER_POSE} frames`}
              >
                {last
                  ? <img src={last} alt={`${label} latest frame`} className="absolute inset-0 size-full object-cover" />
                  : <Video className="size-5 text-muted-foreground" aria-hidden="true" />}
                <span className="absolute bottom-1.5 left-1.5 rounded bg-background/90 px-1.5 py-0.5 text-[11px] font-medium">
                  {label} · {count}/{FRAMES_PER_POSE}
                </span>
                {done && (
                  <span className="absolute top-1.5 right-1.5 rounded-full bg-primary p-0.5 text-primary-foreground">
                    <Check className="size-3" aria-hidden="true" />
                  </span>
                )}
              </div>
            )
          })}
        </div>

        <div className="rounded-lg border bg-muted/40 p-3 text-xs text-muted-foreground" role="status">
          {poseStatus === "loading" ? "Loading on-device head pose checker… Camera preview stays live. This may take a moment on your first visit." : poseStatus === "ready" ? "Head pose checker ready · processing stays on your device" : poseError}
          {poseStatus === "error" && <Button variant="outline" size="sm" className="mt-2" onClick={() => { runId.current += 1; setPhase("ready"); setCaptureError(null); setPoseRetry(value => value + 1) }}>Retry pose checker</Button>}
        </div>

        <div className="text-center" aria-live="polite">
          <h3 className="font-medium">{prompt}</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {phase === "complete"
              ? `${frames} frames collected. Review the thumbnails, then submit.`
              : phase === "transition"
                ? "Keep your face in the guide."
                : running ? guidance : pose.hint}
          </p>
        </div>

        <div className="relative mx-auto aspect-[3/4] max-h-[420px] w-full max-w-[315px] overflow-hidden rounded-xl bg-neutral-950">
          <video
            ref={videoRef}
            muted
            playsInline
            autoPlay
            aria-label="Mirrored live camera preview"
            className="absolute inset-0 size-full -scale-x-100 object-cover"
          />
          {status === "ready" && (phase === "waiting" || phase === "countdown" || phase === "collecting" || phase === "ready") && (
            <div className="pointer-events-none absolute top-[16%] left-1/2 h-[62%] w-[64%] -translate-x-1/2 rounded-[50%] border-2 border-white/70" aria-hidden="true" />
          )}
          {status === "ready" && phase === "countdown" && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/40 text-white">
              <span className="text-6xl font-semibold tabular-nums">{countdown}</span>
              <span className="text-sm">Correct pose — hold still…</span>
            </div>
          )}
          {status === "ready" && phase === "collecting" && (
            <span className="absolute bottom-3 left-1/2 flex -translate-x-1/2 items-center gap-2 rounded-full bg-black/70 px-3 py-1 text-xs text-white">
              <span className="size-2 animate-pulse rounded-full bg-red-500" aria-hidden="true" />
              Collecting {photos[pose.step].length}/{FRAMES_PER_POSE} — hold still
            </span>
          )}
          {status === "ready" && phase === "complete" && (
            <span className="absolute bottom-3 left-1/2 flex -translate-x-1/2 items-center gap-1.5 rounded-full bg-black/70 px-3 py-1 text-xs text-white">
              <Check className="size-3.5" aria-hidden="true" /> Capture complete
            </span>
          )}
          {status !== "ready" && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center text-neutral-300">
              {status === "requesting" ? <Camera className="size-8" aria-hidden="true" /> : <VideoOff className="size-8" aria-hidden="true" />}
              <p className="text-sm font-medium text-white">{status === "requesting" ? "Waiting for camera permission" : "Camera unavailable"}</p>
              <p className="text-xs leading-relaxed">{status === "requesting" ? "Choose Allow in your browser's prompt." : error}</p>
              {status === "error" && (
                <Button variant="secondary" size="sm" onClick={() => void retry()} disabled={submitting}>
                  <RefreshCw aria-hidden="true" /> Try again
                </Button>
              )}
            </div>
          )}
        </div>

        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>{frames} of {FRAMES_PER_POSE * POSES.length} frames</span>
            {running ? <Badge variant="secondary">Live</Badge> : phase === "complete" ? <Badge variant="secondary">Ready to submit</Badge> : null}
          </div>
          <Progress value={progress} aria-label="Capture progress" />
        </div>

        {(captureError || submitError) && (
          <Alert variant="destructive">
            <CircleAlert aria-hidden="true" />
            <AlertDescription>{submitError || captureError}</AlertDescription>
          </Alert>
        )}
      </CardContent>
      <CardFooter className="flex-col gap-3 border-t pt-6 sm:flex-row sm:justify-between">
        <Button variant="ghost" onClick={onBack} disabled={submitting} className="w-full sm:w-auto">
          <ArrowLeft aria-hidden="true" /> Back to details
        </Button>
        <div className="flex w-full gap-2 sm:w-auto">
          {phase === "complete" ? (
            <>
              <Button variant="outline" size="lg" onClick={() => void start()} disabled={submitting} className="flex-1 sm:flex-none">
                <RefreshCw aria-hidden="true" /> Redo capture
              </Button>
              <Button size="lg" onClick={onSubmit} disabled={submitting} className="flex-1 sm:flex-none">
                {submitting ? <Spinner aria-label="Submitting enrollment" /> : <Send aria-hidden="true" />}
                {submitting ? "Submitting…" : "Submit enrollment"}
              </Button>
            </>
          ) : running ? (
            <Button variant="outline" size="lg" onClick={() => void start()} disabled={submitting} className="w-full sm:w-auto">
              <RefreshCw aria-hidden="true" /> Restart capture
            </Button>
          ) : (
            <Button size="lg" onClick={() => void start()} disabled={status !== "ready" || poseStatus !== "ready" || submitting} className="w-full sm:w-auto">
              <Play aria-hidden="true" /> {phase === "error" ? "Restart capture" : "Start guided capture"}
            </Button>
          )}
        </div>
      </CardFooter>
    </Card>
  )
}
