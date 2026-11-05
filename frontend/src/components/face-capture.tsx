import { useState } from "react"
import { ArrowLeft, ArrowRight, Camera, Check, CircleAlert, RefreshCw, Send, VideoOff } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Spinner } from "@/components/ui/spinner"
import { useCamera } from "@/hooks/use-camera"
import { capturePhoto, POSES, type Photos, type PoseStep } from "@/lib/enrollment"
import { cn } from "@/lib/utils"

type Props = {
  photos: Photos
  onChange: (photos: Photos) => void
  onBack: () => void
  onSubmit: () => void
  submitting: boolean
  submitError: string | null
}

export function FaceCapture({ photos, onChange, onBack, onSubmit, submitting, submitError }: Props) {
  const { videoRef, status, error, retry } = useCamera()
  const [active, setActive] = useState<PoseStep>(() => POSES.find(({ step }) => !photos[step])?.step ?? "right")
  const [captureError, setCaptureError] = useState<string | null>(null)
  const pose = POSES.find(({ step }) => step === active)!
  const captured = photos[active]
  const remaining = POSES.filter(({ step }) => !photos[step])
  const next = remaining.find(({ step }) => step !== active)

  function capture() {
    if (!videoRef.current) return
    try {
      onChange({ ...photos, [active]: capturePhoto(videoRef.current) })
      setCaptureError(null)
    } catch (cause) {
      setCaptureError(cause instanceof Error ? cause.message : "Could not capture the photo. Try again.")
    }
  }

  return (
    <Card aria-busy={submitting}>
      <CardHeader>
        <CardTitle className="text-xl">Capture your photos</CardTitle>
        <CardDescription>One at a time, in good light. Keep your whole face inside the guide.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid grid-cols-3 gap-3" aria-label="Photo checklist">
          {POSES.map(({ step, label }) => (
            <div
              key={step}
              className={cn(
                "relative flex aspect-[4/3] items-center justify-center overflow-hidden rounded-lg border bg-muted",
                step === active && "ring-2 ring-primary ring-offset-2 ring-offset-card",
              )}
              aria-label={`${label} photo ${photos[step] ? "captured" : "not captured"}`}
            >
              {photos[step]
                ? <img src={photos[step]!} alt={`${label} capture`} className="absolute inset-0 size-full object-cover" />
                : <Camera className="size-5 text-muted-foreground" aria-hidden="true" />}
              <span className="absolute bottom-1.5 left-1.5 rounded bg-background/90 px-1.5 py-0.5 text-[11px] font-medium">
                {label}
              </span>
              {photos[step] && (
                <span className="absolute top-1.5 right-1.5 rounded-full bg-primary p-0.5 text-primary-foreground">
                  <Check className="size-3" aria-hidden="true" />
                </span>
              )}
            </div>
          ))}
        </div>

        <div className="text-center">
          <h3 className="font-medium">{captured ? `${pose.label} photo captured` : pose.title}</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {captured ? "Review it below. Retake if needed, or continue." : pose.hint}
          </p>
        </div>

        <div className="relative mx-auto aspect-[3/4] max-h-[420px] w-full max-w-[315px] overflow-hidden rounded-xl bg-neutral-950">
          <video
            ref={videoRef}
            muted
            playsInline
            autoPlay
            aria-label="Mirrored camera preview"
            className={cn("absolute inset-0 size-full -scale-x-100 object-cover", captured && "invisible")}
          />
          {captured && <img src={captured} alt={`${pose.label} review`} className="absolute inset-0 size-full object-cover" />}
          {!captured && status === "ready" && (
            <>
              <div className="pointer-events-none absolute top-[16%] left-1/2 h-[62%] w-[64%] -translate-x-1/2 rounded-[50%] border-2 border-white/70" aria-hidden="true" />
              <span className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-black/60 px-3 py-1 text-xs text-white">
                Mirrored preview
              </span>
            </>
          )}
          {!captured && status !== "ready" && (
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
          {captured ? (
            <>
              <Button variant="outline" size="lg" onClick={() => onChange({ ...photos, [active]: null })} disabled={submitting} className="flex-1 sm:flex-none">
                <RefreshCw aria-hidden="true" /> Retake
              </Button>
              {next ? (
                <Button size="lg" onClick={() => setActive(next.step)} disabled={submitting} className="flex-1 sm:flex-none">
                  Next: {next.label} <ArrowRight aria-hidden="true" />
                </Button>
              ) : (
                <Button size="lg" onClick={onSubmit} disabled={submitting} className="flex-1 sm:flex-none">
                  {submitting ? <Spinner aria-label="Submitting enrollment" /> : <Send aria-hidden="true" />}
                  {submitting ? "Submitting…" : "Submit enrollment"}
                </Button>
              )}
            </>
          ) : (
            <Button size="lg" onClick={capture} disabled={status !== "ready" || submitting} className="w-full sm:w-auto">
              <Camera aria-hidden="true" /> Capture {pose.label.toLowerCase()} photo
            </Button>
          )}
        </div>
      </CardFooter>
    </Card>
  )
}
