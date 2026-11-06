import { Check, Clock3, Info, RotateCcw } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import type { Receipt } from "@/lib/enrollment"

export function ReceiptCard({ receipt, onReset }: { receipt: Receipt; onReset: () => void }) {
  const queued = receipt.status === "queued"
  return (
    <Card>
      <CardHeader className="text-center">
        <div className="mx-auto mb-2 flex size-12 items-center justify-center rounded-full bg-muted">
          {queued ? <Clock3 className="size-6" aria-hidden="true" /> : <Check className="size-6" aria-hidden="true" />}
        </div>
        <CardTitle className="text-xl">{queued ? "Capture received" : "You're enrolled"}</CardTitle>
        <CardDescription className="mx-auto max-w-md">
          {queued
            ? "Your submission is in the organizer's inbox. You are not enrolled until the organizer runs the PC sync."
            : "Your face template is saved on the attendance PC for this exam."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="space-y-3 text-sm">
          <div className="flex justify-between gap-4"><dt className="text-muted-foreground">Name</dt><dd className="text-right font-medium">{receipt.fullName}</dd></div>
          <Separator />
          <div className="flex justify-between gap-4"><dt className="shrink-0 text-muted-foreground">Index number</dt><dd className="break-all text-right font-mono font-medium">{receipt.studentNo}</dd></div>
          <Separator />
          <div className="flex justify-between gap-4"><dt className="text-muted-foreground">Frames</dt><dd className="font-medium">{receipt.photoCount} captured</dd></div>
          {receipt.exam && (
            <>
              <Separator />
              <div className="flex justify-between gap-4"><dt className="text-muted-foreground">Exam</dt><dd className="font-medium">{receipt.exam}</dd></div>
            </>
          )}
          <Separator />
          <div className="flex items-center justify-between gap-4">
            <dt className="text-muted-foreground">Status</dt>
            <dd><Badge variant="secondary">{queued ? "Awaiting organizer sync" : "Enrolled"}</Badge></dd>
          </div>
        </dl>
        {queued && (
          <Alert className="mt-5">
            <Info aria-hidden="true" />
            <AlertDescription>Keep your index number for exam day. Contact the organizer before syncing if you need to redo the capture.</AlertDescription>
          </Alert>
        )}
      </CardContent>
      <CardFooter className="justify-center border-t pt-6">
        <Button variant="outline" onClick={onReset}>
          <RotateCcw aria-hidden="true" /> Register another student
        </Button>
      </CardFooter>
    </Card>
  )
}
