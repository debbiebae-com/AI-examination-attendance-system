"use client";
import { useEffect, useState } from "react";
import {
  Camera,
  Smartphone,
  Monitor,
  Download,
  Settings2,
  Square,
  Trash2,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { Exam } from "@/lib/data";

type Job = {
  running: boolean;
  kind: string | null;
  exit_code: number | null;
  log: string[];
  sync_configured: boolean;
  platform?: string;
  camera_info?: {
    camera: number;
    source: "pc" | "droidcam";
    capture_backend: string;
  } | null;
};
type Person = {
  student_no: string;
  full_name: string;
  face_samples: number;
  registered: boolean;
  ready: boolean;
  reasons: string[];
};
type PresentationAction = "register_all" | "clear_attendance" | "reset_display";
type PresentationPlan = {
  token: string;
  action: PresentationAction;
  counts: Record<string, number>;
};
const presentationLabels = {
  register_all: "Register all volunteers",
  clear_attendance: "Clear classroom attendance",
  reset_display: "Reset live display",
};
type Plan = {
  token: string;
  students: { student_no: string; full_name: string }[];
  counts: { embeddings: number; registrations: number; attendance: number };
  warning: string;
};
async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
    signal: AbortSignal.timeout(8000),
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Request failed. Refresh and try again.",
    );
  return data;
}
export function DemoControls({
  disabled = false,
  onChanged,
}: {
  disabled?: boolean;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [exam, setExam] = useState("");
  const [people, setPeople] = useState<Person[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [camera, setCamera] = useState("0");
  const [source, setSource] = useState<"pc" | "droidcam">("pc");
  const [captureBackend, setCaptureBackend] = useState("auto");
  const [query, setQuery] = useState("");
  const [presentationPlan, setPresentationPlan] =
    useState<PresentationPlan | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    if (!open || disabled) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    setReady(false);
    setPeople([]);
    setSelected([]);
    setPlan(null);
    setPresentationPlan(null);
    async function poll() {
      try {
        const [status, list] = await Promise.all([
          api<Job>("control/status"),
          api<Exam[]>("exams"),
        ]);
        const chosen =
          exam ||
          String(
            (list.find((item) => item.course_code === "CS101") || list[0])
              ?.id || "",
          );
        const roster = chosen
          ? await api<Person[]>(`control/readiness?exam_id=${chosen}`)
          : [];
        if (cancelled) return;
        setJob(status);
        setPeople(roster);
        setReady(true);
        setLoadError("");
        if (!exam && chosen) setExam(chosen);
      } catch (e) {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : "Controls unavailable");
          setReady(false);
        }
      } finally {
        if (!cancelled) timer = setTimeout(poll, 2000);
      }
    }
    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [open, exam, disabled, refresh]);
  async function run(path: string, body: unknown) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api<{ message?: string }>(`control/${path}`, body);
      setNotice(result.message || "Task started. Progress appears below.");
      setPlan(null);
      setPresentationPlan(null);
      setConfirmation("");
      setSelected([]);
      setRefresh((r) => r + 1);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Operation failed");
    } finally {
      setBusy(false);
    }
  }
  async function previewPresentation(action: PresentationAction) {
    setBusy(true);
    setError("");
    setNotice("");
    setPlan(null);
    setPresentationPlan(null);
    try {
      setPresentationPlan(
        await api<PresentationPlan>("control/presentation/preview", {
          exam_id: Number(exam),
          action,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Preview failed");
    } finally {
      setBusy(false);
    }
  }
  async function preview(numbers: string[]) {
    setBusy(true);
    setError("");
    setNotice("");
    setPlan(null);
    setPresentationPlan(null);
    setConfirmation("");
    try {
      setPlan(
        await api<Plan>("control/delete/preview", { student_nos: numbers }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Preview failed");
    } finally {
      setBusy(false);
    }
  }
  const locked = busy || !ready || !!job?.running;
  const cameraValid =
    camera !== "" &&
    Number.isInteger(Number(camera)) &&
    Number(camera) >= 0 &&
    Number(camera) <= 10;
  const cameraBody = {
    camera: Number(camera),
    ...(source === "pc" && captureBackend === "auto"
      ? {}
      : { source, capture_backend: captureBackend }),
  };
  const shown = people.filter((p) =>
    `${p.full_name} ${p.student_no}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  return (
    <>
      <Button
        variant="outline"
        disabled={disabled}
        onClick={() => setOpen(true)}
        className="h-9 bg-background text-xs shadow-none"
      >
        <Settings2 />
        Demo controls
      </Button>
      <Dialog
        open={open}
        onOpenChange={(value) => {
          setOpen(value);
          if (!value) {
            setPresentationPlan(null);
            setPlan(null);
            setConfirmation("");
          }
        }}
      >
        <DialogContent className="max-w-3xl">
          <DialogTitle className="text-xl font-semibold">
            Demo controls
          </DialogTitle>
          <DialogDescription className="mt-2 max-w-xl text-xs leading-5 text-muted-foreground">
            Operate this PC’s demonstration. Changes affect your real local
            database, not layout preview data. Stop recognition before syncing,
            registering or removing volunteers.
          </DialogDescription>
          {(error || loadError) && (
            <div
              role="alert"
              className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-900"
            >
              {error || loadError}
            </div>
          )}
          {notice && (
            <p
              role="status"
              className="mt-4 rounded-lg bg-emerald-50 p-3 text-xs text-emerald-900"
            >
              {notice}
            </p>
          )}
          <section
            aria-label="Demonstration classroom"
            className="mt-6 rounded-lg border bg-muted/40 p-4"
          >
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              Classroom
            </p>
            <h3 className="mt-1 text-sm font-semibold">Test classroom 1</h3>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">
              Each recognized student shows a stable, randomly assigned sample
              examination on camera. These are fictional presentation labels—not
              exam registration. Saved attendance and readiness still use the
              classroom's existing backing exam.
            </p>
          </section>
          <section
            aria-label="Camera source setup"
            className="mt-5 rounded-xl border p-4"
          >
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold">Recognition camera</h3>
              <span className="text-[10px] text-muted-foreground">
                PC processes video · phone supplies camera
              </span>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <Button
                variant={source === "pc" ? "secondary" : "outline"}
                aria-pressed={source === "pc"}
                disabled={locked}
                onClick={() => {
                  setSource("pc");
                  setCamera("0");
                  setCaptureBackend("auto");
                }}
              >
                <Monitor />
                PC webcam
              </Button>
              <Button
                variant={source === "droidcam" ? "secondary" : "outline"}
                aria-pressed={source === "droidcam"}
                disabled={locked}
                onClick={() => {
                  setSource("droidcam");
                  setCamera("1");
                  setCaptureBackend(
                    job?.platform === "win32" ? "dshow" : "auto",
                  );
                }}
              >
                <Smartphone />
                Phone / DroidCam
              </Button>
            </div>
            {source === "droidcam" && (
              <div className="mt-3 rounded-lg bg-muted/40 p-3 text-xs leading-5 text-muted-foreground">
                <ol className="list-decimal space-y-1 pl-4">
                  <li>
                    Start DroidCam on the phone and connect it in the Windows
                    DroidCam client using USB or Wi-Fi.
                  </li>
                  <li>
                    Confirm live video in that client. Keep the DroidCam
                    connection running; close Windows Camera, Teams and other
                    apps competing for its virtual webcam.
                  </li>
                  <li>
                    Choose its camera number below, then Check camera. Number 1
                    is only a starting guess—not a detected phone.
                  </li>
                  <li>
                    Confirm the phone image in the brief PC test window, wait
                    for the check to finish, then Start recognition.
                  </li>
                </ol>
                <p className="mt-2">
                  Use the DroidCam virtual webcam driver, not an OBS-only
                  source. USB is preferred for the demo. Start at 720p; avoid
                  4K. This dashboard does not connect directly to a phone IP
                  address.
                </p>
              </div>
            )}
            <label className="space-y-2 text-xs font-medium">
              Camera number
              <Input
                aria-label="Camera number"
                type="number"
                min={0}
                max={10}
                value={camera}
                disabled={locked}
                onChange={(e) => setCamera(e.target.value)}
              />
            </label>
            <label className="mt-3 block space-y-2 text-xs font-medium">
              Capture backend
              <select
                aria-label="Capture backend"
                value={captureBackend}
                disabled={locked}
                onChange={(event) => setCaptureBackend(event.target.value)}
                className="h-10 w-full rounded-md border bg-background px-3 text-xs"
              >
                <option value="auto">Automatic (existing default)</option>
                <option
                  value="dshow"
                  disabled={!!job?.platform && job.platform !== "win32"}
                >
                  DirectShow — Windows / DroidCam
                </option>
                <option
                  value="msmf"
                  disabled={!!job?.platform && job.platform !== "win32"}
                >
                  Media Foundation — Windows alternative
                </option>
              </select>
            </label>
            <p className="mt-2 text-[11px] leading-5 text-muted-foreground">
              Backend platform:{" "}
              {job?.platform ||
                "not reported — restart the updated backend API"}
              .{" "}
              {job?.platform && job.platform !== "win32"
                ? "Windows capture backends are unavailable on this backend host."
                : !job?.platform
                  ? "Windows options are selectable, but the API still validates support. An old API may ignore these settings; restart it before checking."
                  : "DirectShow and Media Foundation are available to select."}{" "}
              {locked
                ? "Source settings are locked until the current task finishes."
                : ""}
            </p>
            <p className="mt-2 text-[11px] leading-5 text-muted-foreground">
              Camera numbers are local to this PC/backend and can change after
              reconnecting. If the wrong feed opens, stop it and try 0, 1, 2…;
              for a black phone feed, try another Windows backend. The camera
              check never records attendance.
            </p>
            <Button
              className="mt-3"
              variant="outline"
              disabled={locked || !cameraValid}
              onClick={() => run("camera/check", cameraBody)}
            >
              <Camera />
              Check camera
            </Button>
            {job?.kind === "camera_check" && (
              <p
                role="status"
                className="mt-3 text-xs leading-5 text-muted-foreground"
              >
                {job.running
                  ? "Checking device… watch the brief preview on your PC. A slow/blocked driver check is stopped after 20 seconds."
                  : job.exit_code === 0
                    ? "Camera check passed: a frame was received. Confirm that the test window showed your intended camera. This is not an identity or attendance check."
                    : "Camera check did not complete successfully. Review the output below, reconnect DroidCam, or try another index/backend."}
              </p>
            )}
            {job?.camera_info && (
              <p className="mt-3 text-[11px] text-muted-foreground">
                Last camera selection:{" "}
                {job.camera_info.source === "droidcam"
                  ? "Phone / DroidCam"
                  : "PC webcam"}{" "}
                · device #{job.camera_info.camera} ·{" "}
                {job.camera_info.capture_backend}. Source name is your
                selection, not automatic device identification.
              </p>
            )}
          </section>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              className="bg-primary text-primary-foreground hover:bg-primary/90"
              disabled={locked || !exam || !cameraValid}
              onClick={() =>
                run("camera/start", {
                  exam_id: Number(exam),
                  ...cameraBody,
                  demo_classroom: true,
                })
              }
            >
              <Camera />
              Start recognition
            </Button>
            <Button
              variant="outline"
              disabled={
                busy || !ready || !job?.running || job.kind !== "camera"
              }
              onClick={() => run("camera/stop", {})}
            >
              <Square />
              Stop camera
            </Button>
            <Button
              variant="outline"
              disabled={locked || !exam || !job?.sync_configured}
              onClick={() => run("sync", { exam_id: Number(exam) })}
            >
              <Download />
              Sync submissions
            </Button>
          </div>
          <p className="mt-3 text-[11px] leading-5 text-muted-foreground">
            {job?.sync_configured
              ? "Sync imports pending phone submissions and wipes cloud photos after successful sync. It uses each submission’s exam, falling back to this classroom’s backing exam."
              : "Sync needs SUPABASE_URL and SUPABASE_SERVICE_KEY configured on the backend PC once. Never enter the service key in the browser."}{" "}
            Recognition opens the PC camera window; results flow into the live
            dashboard.
          </p>
          <div className="mt-5 rounded-lg border bg-muted/40 p-3">
            <p className="text-xs font-medium">
              {job?.running
                ? `${job.kind === "camera" ? "Recognition" : job.kind === "camera_check" ? "Camera check" : "Sync"} task running`
                : job?.kind
                  ? `${job.kind} finished · exit ${job.exit_code ?? "pending"}`
                  : "No dashboard task running"}
            </p>
            <p className="mt-1 text-[10px] text-muted-foreground">
              Stop is cooperative: allow the current frame/model loading to
              finish. For a camera started in a terminal, press q in that camera
              window instead.
            </p>
            {!!job?.log.length && (
              <pre
                aria-label="Demo task output"
                className="mt-3 max-h-36 overflow-auto whitespace-pre-wrap break-all text-[10px] leading-4 text-muted-foreground"
              >
                {job.log.join("\n")}
              </pre>
            )}
          </div>
          <section
            aria-label="Presentation Tools"
            className="mt-7 border-t pt-6"
          >
            <h3 className="text-sm font-semibold">Presentation Tools</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Prepare and manage your ExamLens demonstration. Stop recognition
              before using these tools.
            </p>
            <div className="mt-4 space-y-4">
              {(
                [
                  [
                    "register_all",
                    "Registers all locally enrolled volunteers for Test classroom 1. Fee and suspension rules stay unchanged.",
                  ],
                  [
                    "clear_attendance",
                    "Start another round. Clears only classroom attendance; keeps students, face data and registrations.",
                  ],
                  [
                    "reset_display",
                    "Clears activity and live counters only. Saved attendance and attendance-based totals stay unchanged.",
                  ],
                ] as const
              ).map(([action, description]) => (
                <div
                  key={action}
                  className="flex flex-wrap items-center justify-between gap-3"
                >
                  <p className="max-w-sm text-xs leading-5 text-muted-foreground">
                    {description}
                  </p>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={locked || !exam}
                    onClick={() => previewPresentation(action)}
                  >
                    {presentationLabels[action]}
                  </Button>
                </div>
              ))}
            </div>
            {presentationPlan && (
              <div
                role="region"
                aria-label="Confirm presentation action"
                className="mt-4 rounded-lg border p-4"
              >
                <h4 className="text-sm font-semibold">
                  Review: {presentationLabels[presentationPlan.action]}
                </h4>
                <p className="mt-2 text-xs">
                  Test classroom 1 · Preview expires after two minutes.
                </p>
                <ul className="mt-2 text-xs">
                  {Object.entries(presentationPlan.counts).map(
                    ([key, count]) => (
                      <li key={key}>
                        {key.replaceAll("_", " ")}: {count}
                      </li>
                    ),
                  )}
                </ul>
                <p className="mt-2 text-xs text-muted-foreground">
                  {presentationPlan.action === "clear_attendance"
                    ? "Attendance deletion cannot be undone. Students, faces and registrations are preserved. Start recognition again for the next round."
                    : presentationPlan.action === "reset_display"
                      ? "Only the live feed and its counters are cleared. Saved attendance is not deleted."
                      : "Existing registrations are kept; only missing registrations are added."}
                </p>
                <div className="mt-3 flex gap-2">
                  <Button
                    size="sm"
                    variant={
                      presentationPlan.action === "clear_attendance"
                        ? "destructive"
                        : "outline"
                    }
                    disabled={locked}
                    onClick={() =>
                      run("presentation/confirm", {
                        token: presentationPlan.token,
                        confirmation: "CONFIRM",
                      })
                    }
                  >
                    Confirm{" "}
                    {presentationLabels[presentationPlan.action].toLowerCase()}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    onClick={() => setPresentationPlan(null)}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            )}
          </section>
          <section className="mt-7 border-t pt-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold">Demo volunteers</h3>
                <p className="mt-1 text-[11px] text-muted-foreground">
                  {selected.length} selected · {people.length} stored locally
                </p>
              </div>
              <Button
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() => setRefresh((r) => r + 1)}
              >
                <RefreshCw />
                Refresh
              </Button>
            </div>
            <Input
              aria-label="Search volunteers"
              placeholder="Search name or index number"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="mt-4"
            />
            <div className="mt-3 max-h-64 overflow-auto rounded-lg border">
              <table className="w-full text-left text-xs">
                <thead className="sticky top-0 bg-muted/40 text-[10px] text-muted-foreground">
                  <tr>
                    <th className="p-3">
                      <input
                        type="checkbox"
                        aria-label="Select all visible volunteers"
                        disabled={locked || !shown.length}
                        checked={
                          !!shown.length &&
                          shown.every((p) => selected.includes(p.student_no))
                        }
                        onChange={(e) => {
                          setPlan(null);
                          setSelected(
                            e.target.checked
                              ? [
                                  ...new Set([
                                    ...selected,
                                    ...shown.map((p) => p.student_no),
                                  ]),
                                ]
                              : selected.filter(
                                  (n) => !shown.some((p) => p.student_no === n),
                                ),
                          );
                        }}
                      />
                    </th>
                    <th className="p-3">Volunteer</th>
                    <th className="p-3">Face samples</th>
                    <th className="p-3">Readiness</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((p) => (
                    <tr key={p.student_no} className="border-t">
                      <td className="p-3">
                        <input
                          type="checkbox"
                          aria-label={`Select ${p.full_name}`}
                          checked={selected.includes(p.student_no)}
                          disabled={locked}
                          onChange={(e) => {
                            setPlan(null);
                            setSelected(
                              e.target.checked
                                ? [...selected, p.student_no]
                                : selected.filter((n) => n !== p.student_no),
                            );
                          }}
                        />
                      </td>
                      <td className="p-3">
                        <span className="font-medium">{p.full_name}</span>
                        <span className="mt-1 block text-[10px] text-muted-foreground">
                          {p.student_no}
                        </span>
                      </td>
                      <td className="p-3">{p.face_samples}</td>
                      <td className="p-3">
                        <span
                          className={
                            p.ready ? "text-emerald-700" : "text-amber-800"
                          }
                        >
                          {p.ready ? "Ready" : p.reasons.join(" · ")}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!shown.length && (
                <p className="p-5 text-center text-xs text-muted-foreground">
                  {ready
                    ? "No matching volunteers. Sync phone submissions to add them."
                    : "Loading volunteer readiness…"}
                </p>
              )}
            </div>
            <details className="mt-4 rounded-lg border p-3">
              <summary className="cursor-pointer text-xs font-medium">
                Advanced student deletion
              </summary>
              <p className="mt-2 text-xs text-muted-foreground">
                These tools permanently delete student data, not just
                attendance. Select volunteers above before proceeding.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={locked || !selected.length}
                  onClick={() => preview(selected)}
                >
                  <Trash2 />
                  Remove selected…
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={
                    locked ||
                    !selected.length ||
                    selected.length === people.length
                  }
                  onClick={() =>
                    preview(
                      people
                        .filter((p) => !selected.includes(p.student_no))
                        .map((p) => p.student_no),
                    )
                  }
                >
                  Delete other students…
                </Button>
              </div>
              <p className="mt-3 text-[10px] leading-5 text-muted-foreground">
                Registration does not change fee/suspension flags. Removal
                deletes local students, face embeddings, registrations and
                attendance. Exams and Supabase inbox submissions are preserved.
              </p>
            </details>
          </section>
          {plan && (
            <section
              aria-label="Confirm local deletion"
              className="mt-6 rounded-xl border border-red-200 bg-red-50 p-5"
            >
              <h3 className="text-sm font-semibold text-red-900">
                Review deletion: {plan.students.length} student(s)
              </h3>
              <ul className="mt-3 max-h-32 overflow-auto text-xs text-red-900">
                {plan.students.map((p) => (
                  <li key={p.student_no} className="py-1">
                    {p.full_name} · {p.student_no}
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-xs leading-5 text-red-900">
                Also removes {plan.counts.embeddings} face samples,{" "}
                {plan.counts.registrations} registrations and{" "}
                {plan.counts.attendance} attendance records. This cannot be
                undone.
              </p>
              <p className="mt-2 text-[11px] leading-5 text-red-800">
                {plan.warning} Preview expires after two minutes.
              </p>
              <label className="mt-4 block text-xs font-medium text-red-900">
                Type DELETE to confirm
                <Input
                  aria-label="Deletion confirmation"
                  className="mt-2 bg-background"
                  value={confirmation}
                  onChange={(e) => setConfirmation(e.target.value)}
                />
              </label>
              <div className="mt-3 flex gap-2">
                <Button
                  variant="destructive"
                  disabled={
                    busy || !ready || job?.running || confirmation !== "DELETE"
                  }
                  onClick={() =>
                    run("delete/confirm", { token: plan.token, confirmation })
                  }
                >
                  Permanently remove
                </Button>
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => {
                    setPlan(null);
                    setConfirmation("");
                  }}
                >
                  Cancel
                </Button>
              </div>
            </section>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
