import { useState } from "react"
import { ScanFace, ShieldCheck } from "lucide-react"
import { DetailsForm } from "@/components/details-form"
import { FaceCapture } from "@/components/face-capture"
import { ReceiptCard } from "@/components/receipt-card"
import { Stepper } from "@/components/stepper"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { enrollmentConfig, usesInbox } from "@/lib/config"
import { emptyPhotos, submitEnrollment, type Photos, type Receipt, type StudentDetails } from "@/lib/enrollment"

type Stage = "details" | "camera" | "receipt"

export default function App() {
  const [stage, setStage] = useState<Stage>("details")
  const [details, setDetails] = useState<StudentDetails>({ fullName: "", studentNo: "" })
  const [photos, setPhotos] = useState<Photos>(emptyPhotos)
  const [receipt, setReceipt] = useState<Receipt | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const current = stage === "details" ? 0 : stage === "camera" ? 1 : 2

  async function handleSubmit() {
    if (submitting) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      const result = await submitEnrollment(details, photos, enrollmentConfig)
      setReceipt(result)
      setStage("receipt")
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Submission failed. Please try again.")
    } finally {
      setSubmitting(false)
    }
  }

  function reset() {
    setStage("details")
    setDetails({ fullName: "", studentNo: "" })
    setPhotos(emptyPhotos())
    setReceipt(null)
    setSubmitError(null)
  }

  return (
    <div className="flex min-h-svh flex-col">
      <header className="border-b bg-card">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-2.5">
            <span className="flex size-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <ScanFace className="size-5" aria-hidden="true" />
            </span>
            <span className="text-sm font-semibold tracking-tight">Exam attendance</span>
          </div>
          <Badge variant="outline" className="font-normal text-muted-foreground">
            {usesInbox() ? "Online intake" : "Student registration"}
          </Badge>
        </div>
      </header>

      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-8 sm:px-6 sm:py-12">
        <div className="mb-8 space-y-2">
          <p className="text-xs font-medium tracking-widest text-muted-foreground uppercase">Student enrollment</p>
          <h1 className="text-3xl font-semibold tracking-tight text-balance">Register your face</h1>
          <p className="text-sm text-muted-foreground sm:text-base">A short guided capture. Faster check-in on exam day.</p>
        </div>
        <div className="mb-6"><Stepper current={current} /></div>
        <div aria-live="polite" className="sr-only">Step {current + 1} of 3: {["Details", "Capture", "Confirmation"][current]}</div>

        {stage === "details" && (
          <DetailsForm initial={details} onContinue={(value) => { setDetails(value); setStage("camera") }} />
        )}
        {stage === "camera" && (
          <FaceCapture
            photos={photos}
            onChange={setPhotos}
            onBack={() => { setStage("details"); setSubmitError(null) }}
            onSubmit={() => void handleSubmit()}
            submitting={submitting}
            submitError={submitError}
          />
        )}
        {stage === "receipt" && receipt && <ReceiptCard receipt={receipt} onReset={reset} />}

        <div className="mt-6 flex items-start justify-center gap-2 px-4 text-center text-xs leading-relaxed text-muted-foreground">
          <ShieldCheck className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          <p>These frames are collected for exam identity verification and attendance.</p>
        </div>
      </main>

      <footer className="mx-auto w-full max-w-5xl px-4 pb-6 sm:px-6">
        <Separator className="mb-4" />
        <p className="text-center text-xs text-muted-foreground">Exam attendance · Student registration</p>
      </footer>
    </div>
  )
}
