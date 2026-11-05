import { useState, type FormEvent } from "react"
import { ArrowRight, CircleAlert } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { StudentDetails } from "@/lib/enrollment"

type Errors = Partial<Record<"fullName" | "studentNo" | "consent", string>>

export function DetailsForm({ initial, onContinue }: { initial: StudentDetails; onContinue: (details: StudentDetails) => void }) {
  const [fullName, setFullName] = useState(initial.fullName)
  const [studentNo, setStudentNo] = useState(initial.studentNo)
  const [consent, setConsent] = useState(false)
  const [errors, setErrors] = useState<Errors>({})

  function submit(event: FormEvent) {
    event.preventDefault()
    const next: Errors = {}
    if (fullName.trim().length < 2) next.fullName = "Enter your full name."
    if (!studentNo.trim()) next.studentNo = "Enter your index number."
    if (!consent) next.consent = "Consent is required to collect your photos."
    setErrors(next)
    if (Object.keys(next).length) return
    onContinue({ fullName: fullName.trim(), studentNo: studentNo.trim().toUpperCase() })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl">Student details</CardTitle>
        <CardDescription>Use the name and index number on your exam registration.</CardDescription>
      </CardHeader>
      <form onSubmit={submit} noValidate>
        <CardContent className="space-y-5">
          {Object.keys(errors).length > 0 && (
            <Alert variant="destructive">
              <CircleAlert aria-hidden="true" />
              <AlertTitle>Check your details</AlertTitle>
              <AlertDescription>Complete the highlighted fields below.</AlertDescription>
            </Alert>
          )}
          <div className="space-y-2">
            <Label htmlFor="full-name">Full name</Label>
            <Input
              id="full-name"
              name="name"
              autoComplete="name"
              placeholder="e.g. Ama Mensah"
              className="h-11"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              aria-invalid={Boolean(errors.fullName)}
              aria-describedby={errors.fullName ? "full-name-error" : undefined}
              required
            />
            {errors.fullName && <p id="full-name-error" className="text-sm text-destructive">{errors.fullName}</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="index-number">Index number</Label>
            <Input
              id="index-number"
              name="index-number"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              placeholder="e.g. PS/CSC/24/0016"
              maxLength={32}
              className="h-11 font-mono"
              value={studentNo}
              onChange={(event) => setStudentNo(event.target.value)}
              aria-invalid={Boolean(errors.studentNo)}
              aria-describedby={errors.studentNo ? "index-number-error" : "index-number-hint"}
              required
            />
            {errors.studentNo
              ? <p id="index-number-error" className="text-sm text-destructive">{errors.studentNo}</p>
              : <p id="index-number-hint" className="text-xs text-muted-foreground">Enter it exactly as printed, including slashes. It links your capture to your exam record.</p>}
          </div>
          <div className="rounded-lg border bg-muted/40 p-4">
            <div className="flex items-start gap-3">
              <Checkbox
                id="consent"
                className="mt-0.5"
                checked={consent}
                onCheckedChange={(checked) => setConsent(checked === true)}
                aria-invalid={Boolean(errors.consent)}
                aria-describedby="consent-description"
              />
              <Label htmlFor="consent" className="block text-sm leading-relaxed font-normal">
                I consent to the exam organizer collecting a short guided face capture (multiple frames) and creating a face template for exam identity verification and attendance.
              </Label>
            </div>
            <p id="consent-description" className="mt-2 pl-7 text-xs text-muted-foreground">
              You can review the collected frames before submitting.
            </p>
            {errors.consent && <p className="mt-2 pl-7 text-sm text-destructive">{errors.consent}</p>}
          </div>
        </CardContent>
        <CardFooter className="mt-6 flex-col gap-3 border-t pt-6 sm:flex-row sm:justify-between">
          <span className="text-xs text-muted-foreground">Step 1 of 3</span>
          <Button type="submit" size="lg" className="w-full sm:w-auto">
            Continue to capture <ArrowRight aria-hidden="true" />
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}
