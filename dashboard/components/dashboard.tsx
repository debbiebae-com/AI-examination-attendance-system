"use client";

import { useEffect, useRef, useState } from "react";
import { Card as ThemeCard, Heading, Text } from "@radix-ui/themes";
import {
  Activity,
  Bell,
  Monitor,
  Info,
  ArrowDownToLine,
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronRight,
  CircleHelp,
  Clock3,
  Database,
  LayoutDashboard,
  Menu,
  Radio,
  RefreshCw,
  ScanFace,
  Search,
  Users,
  WifiOff,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  academic,
  csv,
  eventLabel,
  initials,
  statusLabel,
  time,
  visibleStudents,
  type Feed,
  type Student,
} from "@/lib/data";
import { AttendanceCharts } from "@/components/attendance-charts";
import { DemoControls } from "@/components/demo-controls";
import { demoFeed } from "@/lib/demo";

async function get<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`/api/${path}`, { signal, cache: "no-store" });
  if (!response.ok)
    throw new Error(
      response.status === 503
        ? "Local API is offline. Start the backend on this PC to connect."
        : `Could not load attendance data (${response.status}).`,
    );
  return response.json();
}

function Avatar({ name, large = false }: { name: string; large?: boolean }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-md border bg-muted/50 font-medium text-muted-foreground ${large ? "size-12 text-base" : "size-8 text-[11px]"}`}
      aria-label="Initials placeholder — no portrait available"
    >
      {initials(name)}
    </span>
  );
}

function AttendanceBadge({ present }: { present: boolean }) {
  return (
    <Badge
      variant="outline"
      className={
        present
          ? "table-status gap-1.5 rounded-md border-emerald-200 bg-emerald-50 text-emerald-800"
          : "table-status gap-1.5 rounded-md text-muted-foreground"
      }
    >
      {present ? <Check className="size-3" /> : <Clock3 className="size-3" />}
      {present ? "Present" : "Not recorded"}
    </Badge>
  );
}

export function Dashboard() {
  const [feed, setFeed] = useState<Feed | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [illustration, setIllustration] = useState(false);
  const [retry, setRetry] = useState(0);
  const [checked, setChecked] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Student | null>(null);
  const [tab, setTab] = useState<"all" | "present">("all");
  const [help, setHelp] = useState(false);
  const [section, setSection] = useState("#overview");
  const [navOpen, setNavOpen] = useState(false);
  const [history, setHistory] = useState<number[][]>([]);
  const historySession = useRef<string | null | undefined>(undefined);
  const quickSearch = useRef<HTMLInputElement>(null);
  const recordSearch = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        const input =
          quickSearch.current && quickSearch.current.offsetWidth
            ? quickSearch.current
            : recordSearch.current;
        input?.focus();
        input?.scrollIntoView({ block: "center" });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => {
    if (!feed) {
      setHistory([]);
      return;
    }
    const changed = historySession.current !== feed.session.session_id;
    historySession.current = feed.session.session_id;
    const sample = [
      feed.attendance.length,
      feed.session.identified_count ??
        new Set(
          feed.session.events
            .filter((event) => event.kind === "identified")
            .map((event) => event.student_no),
        ).size,
      feed.session.unidentified_now,
      feed.session.processed_fps ?? 0,
    ];
    setHistory((previous) => [...(changed ? [] : previous).slice(-4), sample]);
  }, [feed]);
  const previousSession = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    setChecked([]);
    if (illustration) {
      setFeed(demoFeed());
      setError("");
      setLoading(false);
      return;
    }
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController;
    setLoading(true);
    setFeed(null);
    setSelected(null);
    async function poll() {
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 8000);
      try {
        const [session, students] = await Promise.all([
          get<Feed["session"]>("live/session", controller.signal),
          get<Student[]>("students", controller.signal),
        ]);
        const attendance = session.exam
          ? await get<Feed["attendance"]>(
              `exams/${session.exam.id}/attendance`,
              controller.signal,
            )
          : [];
        if (!disposed) {
          if (previousSession.current !== session.session_id) {
            setSelected(null);
            setChecked([]);
          }
          previousSession.current = session.session_id;
          setFeed({ session, students, attendance });
          setError("");
        }
      } catch (e) {
        if (!disposed)
          setError(
            e instanceof Error && e.name !== "AbortError"
              ? e.message
              : "Connection timed out. Retrying the local API…",
          );
      } finally {
        clearTimeout(timeout);
        if (!disposed) {
          setLoading(false);
          timer = setTimeout(poll, 2000);
        }
      }
    }
    poll();
    return () => {
      disposed = true;
      clearTimeout(timer);
      controller?.abort();
    };
  }, [illustration, retry]);

  const live = feed?.session;
  const exam = live?.exam;
  const active = !error && live?.status === "running";
  const students = feed
    ? visibleStudents(feed, query).filter(
        (s) =>
          tab !== "present" ||
          feed.attendance.some((a) => a.student_no === s.student_no),
      )
    : [];
  const nameFor = (id?: string | null) =>
    feed?.students.find((s) => s.student_no === id)?.full_name || id;
  const latestStudent = feed ? visibleStudents(feed, "")[0] : null;
  const latestAcademic = latestStudent ? academic(latestStudent) : null;
  const selectedAcademic = selected ? academic(selected) : null;
  const selectedRecord = feed?.attendance.find(
    (a) => a.student_no === selected?.student_no,
  );
  const selectedRecognition = live?.events
    .filter(
      (e) => e.student_no === selected?.student_no && e.kind === "identified",
    )
    .at(-1);
  function exportAttendance(onlySelected = false) {
    if (!feed) return;
    const url = URL.createObjectURL(
      new Blob(
        [
          "\uFEFF" +
            csv(
              onlySelected
                ? feed.attendance.filter((record) =>
                    checked.includes(record.student_no),
                  )
                : feed.attendance,
              exam,
            ),
        ],
        {
          type: "text/csv;charset=utf-8;",
        },
      ),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `${illustration ? "ILLUSTRATION-" : ""}attendance-${exam?.course_code || "exam"}${onlySelected ? "-selected" : ""}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  const identified =
    live?.identified_count ??
    new Set(
      live?.events
        .filter((e) => e.kind === "identified")
        .map((e) => e.student_no)
        .filter(Boolean),
    ).size;
  const lastRecord = feed?.attendance.find(
    (record) => record.student_no === latestStudent?.student_no,
  );
  const metrics = [
    {
      label: "Present",
      value: feed && !error ? feed.attendance.length : "—",
      note: live?.demo_mode
        ? "Saved demonstration records"
        : "Saved examination records",
    },
    {
      label: "Identified",
      value: feed && !error ? identified : "—",
      note: "Distinct identities this session",
    },
    {
      label: "Unidentified",
      value: feed && !error ? (live?.unidentified_now ?? 0) : "—",
      note: "Unmatched tracks in view",
    },
    {
      label: "Processing rate",
      value:
        !error && live?.processed_fps != null
          ? `${live.processed_fps.toFixed(1)}`
          : "—",
      note:
        live?.processed_fps != null
          ? "Processed frames / second"
          : "Available when camera is running",
    },
  ];
  return (
    <div className="dashboard-canvas min-h-screen text-foreground">
      <a
        href="#overview"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-md focus:bg-background focus:p-3"
      >
        Skip to content
      </a>
      {navOpen && (
        <button
          aria-label="Close navigation"
          onClick={() => setNavOpen(false)}
          className="fixed inset-0 z-30 bg-black/40 md:hidden"
        />
      )}
      <aside
        aria-label="Workspace navigation"
        className={`${navOpen ? "flex" : "hidden"} palette-sidebar fixed inset-y-0 left-0 z-40 w-56 flex-col border-r md:flex`}
      >
        <a
          href="#overview"
          onClick={() => setNavOpen(false)}
          className="flex h-14 items-center gap-2.5 border-b px-5"
        >
          <span className="grid size-8 place-items-center rounded-md bg-primary text-primary-foreground">
            <ScanFace className="size-4" />
          </span>
          <span className="text-sm font-semibold tracking-tight">ExamLens</span>
        </a>
        <div className="p-3">
          <div className="mb-5 rounded-md border bg-background px-3 py-2.5">
            <p className="text-xs font-medium">Examination workspace</p>
            <p className="mt-1 text-[11px] text-muted-foreground">
              Local demonstration
            </p>
          </div>
          <p className="mb-2 px-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
            Main Menu
          </p>
          <nav className="space-y-1">
            {[
              ["#overview", "Overview", LayoutDashboard],
              ["#students", "Attendance", Users],
              ["#activity", "Activity log", Activity],
            ].map(([href, label, Icon]) => {
              const NavIcon = Icon as typeof Activity;
              return (
                <div key={String(href)}>
                  {href === "#activity" && (
                    <p className="mb-2 mt-6 px-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                      Monitoring
                    </p>
                  )}
                  <a
                    href={String(href)}
                    onClick={() => {
                      setNavOpen(false);
                      setSection(String(href));
                    }}
                    aria-current={section === href ? "location" : undefined}
                    className="palette-nav-link flex items-center gap-2.5 rounded-md px-2.5 py-2 text-xs font-medium"
                  >
                    <NavIcon className="size-4" />
                    {String(label)}
                  </a>
                </div>
              );
            })}
          </nav>
        </div>
        <div className="mt-auto space-y-3 border-t p-3">
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start text-xs text-muted-foreground"
            onClick={() => {
              setHelp(true);
              setNavOpen(false);
            }}
          >
            <CircleHelp />
            Demo guide
          </Button>
          <div className="flex items-center gap-2 rounded-lg border p-2">
            <span className="grid size-8 place-items-center rounded-full border border-primary/40 bg-primary/15 text-xs font-semibold text-primary">
              LO
            </span>
            <div>
              <p className="text-xs font-medium">Local operator</p>
              <p className="mt-0.5 text-[10px] text-muted-foreground">
                Presentation workspace
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 px-2 text-[11px] text-muted-foreground">
            <Database className="size-3.5" />
            <span>Local database</span>
            <span
              className={`ml-auto size-1.5 rounded-full ${error ? "bg-amber-500" : "bg-neutral-400"}`}
            />
          </div>
        </div>
      </aside>
      <div className="min-w-0 md:ml-56">
        <header className="palette-topbar flex h-14 items-center justify-between gap-3 border-b px-4 sm:px-7">
          <div className="flex min-w-0 items-center gap-3">
            <Button
              variant="ghost"
              size="icon-sm"
              className="md:hidden"
              aria-label="Toggle navigation"
              aria-expanded={navOpen}
              onClick={() => setNavOpen(!navOpen)}
            >
              {navOpen ? <X /> : <Menu />}
            </Button>
            <span className="text-xs text-muted-foreground">Dashboard</span>
            <ChevronRight className="size-3 text-muted-foreground" />
            <span className="text-xs font-medium">
              {section === "#students"
                ? "Attendance"
                : section === "#activity"
                  ? "Activity log"
                  : "Overview"}
            </span>
          </div>
          <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
            <div className="relative hidden lg:block">
              <Search className="absolute left-3 top-2.5 size-3.5" />
              <Input
                ref={quickSearch}
                aria-label="Workspace search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter")
                    document.getElementById("students")?.scrollIntoView();
                }}
                placeholder="Search students…"
                className="h-8 w-56 bg-muted pl-9 pr-12 text-xs"
              />
              <kbd className="pointer-events-none absolute right-2 top-2 rounded border px-1 text-[10px]">
                ⌘ K
              </kbd>
            </div>
            <Button
              variant="outline"
              size="icon-sm"
              aria-label="View recognition activity"
              onClick={() => {
                setSection("#activity");
                document.getElementById("activity")?.scrollIntoView();
              }}
            >
              <Bell className="size-4" />
            </Button>
            <Button
              variant="outline"
              size="icon-sm"
              className="hidden sm:inline-flex"
              aria-label="Toggle fullscreen"
              onClick={() => {
                if (document.fullscreenElement)
                  void document.exitFullscreen().catch(() => {});
                else
                  void document.documentElement
                    .requestFullscreen?.()
                    .catch(() => {});
              }}
            >
              <Monitor className="size-4" />
            </Button>

            <span
              className={`size-1.5 rounded-full ${error ? "bg-amber-500" : active ? "bg-emerald-600" : "bg-neutral-400"}`}
            />
            {illustration
              ? "Preview mode"
              : error
                ? "API disconnected"
                : active
                  ? "Local · connected"
                  : "Local workspace"}
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => setHelp(true)}
              aria-label="Open demo guide"
            >
              <CircleHelp className="size-4" />
            </Button>
          </div>
        </header>
        <main
          id="overview"
          className="mx-auto max-w-[1600px] space-y-6 p-4 sm:p-7 lg:p-8"
        >
          <div className="palette-page-heading flex flex-wrap items-start justify-between gap-4">
            <div>
              <Heading as="h1" size="6" weight="medium">
                Attendance overview
              </Heading>
              <p className="mt-1.5 text-sm text-muted-foreground">
                Recognition session and saved examination records.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <DemoControls
                disabled={illustration || !!error}
                onChanged={() => setRetry((r) => r + 1)}
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIllustration(!illustration)}
              >
                {illustration ? <Radio /> : <BookOpen />}
                {illustration ? "Connect live data" : "Preview layout"}
              </Button>
              <Button
                size="sm"
                disabled={!feed?.attendance.length || !!error}
                onClick={() => exportAttendance()}
              >
                <ArrowDownToLine />
                Export attendance
              </Button>
            </div>
          </div>
          {illustration && (
            <div
              role="status"
              className="illustration-notice flex flex-wrap items-center justify-between gap-2 rounded-md border border-dashed bg-muted/40 px-4 py-3 text-xs text-muted-foreground"
            >
              <span>
                <strong className="font-medium text-foreground">
                  Illustrative preview.
                </strong>{" "}
                Fictional people and records. Not live system data.
              </span>
              <Button
                variant="ghost"
                size="xs"
                onClick={() => setIllustration(false)}
              >
                Exit preview
                <X className="size-3" />
              </Button>
            </div>
          )}
          {error && (
            <div
              role="alert"
              className="flex flex-wrap items-center gap-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-950"
            >
              <WifiOff className="size-4 shrink-0" />
              <span className="min-w-0 flex-1">
                {error}{" "}
                {feed
                  ? "Last successful values are shown and may be stale."
                  : "No live values are shown."}
              </span>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setRetry((r) => r + 1)}
              >
                <RefreshCw />
                Retry
              </Button>
            </div>
          )}
          {live?.error && !error && (
            <div
              role="alert"
              className="rounded-md border border-destructive/25 bg-destructive/5 p-3 text-xs text-destructive"
            >
              Camera session: {live.error}
            </div>
          )}
          <Card className="gap-0 overflow-hidden py-0 shadow-none">
            <CardContent className="p-0">
              <div className="palette-exam-heading flex flex-wrap items-center justify-between gap-4 border-b px-5 py-4">
                <div className="flex min-w-0 items-center gap-3">
                  <Badge
                    variant="secondary"
                    className="rounded-md font-mono text-xs"
                  >
                    {live?.demo_classroom
                      ? "DEMONSTRATION"
                      : exam?.course_code || "No exam"}
                  </Badge>
                  <h2 className="text-sm font-medium">
                    {live?.demo_classroom
                      ? "Recognition demonstration"
                      : exam?.course_title || "No examination selected"}
                  </h2>
                </div>
                <Badge
                  variant="outline"
                  className="gap-2 rounded-md font-normal"
                >
                  <span
                    className={`size-1.5 rounded-full ${active ? "bg-emerald-600" : "bg-neutral-400"}`}
                  />
                  {loading
                    ? "Connecting…"
                    : error
                      ? "Connection unavailable"
                      : statusLabel(live?.status || "idle")}
                </Badge>
              </div>
              <dl className="grid grid-cols-2 gap-x-5 gap-y-4 px-5 py-4 text-xs lg:grid-cols-4">
                {[
                  [
                    "Venue",
                    live?.demo_classroom
                      ? "Recognition demonstration"
                      : exam?.hall || "Not selected",
                  ],
                  [
                    live?.demo_mode ? "Recording mode" : "Scheduled time",
                    live?.demo_mode
                      ? "Enrolled faces · demonstration only"
                      : exam
                        ? `${time(exam.starts_at)} – ${time(exam.ends_at)} GMT`
                        : "No schedule",
                  ],
                  [
                    "Session started",
                    live?.started_at
                      ? `${time(live.started_at)} GMT`
                      : "Not started",
                  ],
                  [
                    "Camera source",
                    live?.camera_source
                      ? `${live.camera_source === "droidcam" ? "Phone / DroidCam" : "PC webcam"} · #${live.camera_index ?? 0} · ${live.camera_backend || "auto"}`
                      : illustration
                        ? "Illustrative fixture"
                        : "Local attendance database",
                  ],
                ].map(([label, value]) => (
                  <div key={label}>
                    <dt className="text-muted-foreground">{label}</dt>
                    <dd className="mt-1.5 break-words font-medium">{value}</dd>
                  </div>
                ))}
              </dl>
            </CardContent>
          </Card>
          <section
            aria-label="Session statistics"
            className="grid grid-cols-2 gap-3 lg:grid-cols-4"
          >
            {metrics.map((metric, index) => (
              <ThemeCard
                key={metric.label}
                size="3"
                variant="surface"
                className="palette-stat"
              >
                <Text as="p" className="metric-label">
                  {metric.label}
                </Text>
                <div className="mt-3 flex items-center justify-between gap-4">
                  <Heading
                    as="h2"
                    size="7"
                    weight="bold"
                    className="tabular-nums"
                  >
                    {metric.value}
                  </Heading>
                  <div
                    className="spark-bars"
                    role="img"
                    aria-label={`${metric.label}: ${!error ? history.length : 0} recent snapshots`}
                  >
                    {!error &&
                      history.map((sample, position) => (
                        <span
                          key={position}
                          title={String(sample[index])}
                          style={{
                            height: `${Math.max(4, (sample[index] / Math.max(1, ...history.map((point) => point[index]))) * 40)}px`,
                          }}
                        />
                      ))}
                  </div>
                </div>
                <Text as="p" className="metric-note flex items-center gap-1.5">
                  <Info className="size-3 shrink-0" />
                  {metric.note}
                </Text>
              </ThemeCard>
            ))}
          </section>
          <AttendanceCharts
            feed={feed}
            offline={!!error}
            illustration={illustration}
          />
          <div className="min-w-0 space-y-5">
            <section id="students" className="min-w-0">
              <Tabs
                value={tab}
                onValueChange={(value) => setTab(value as "all" | "present")}
                className="gap-0"
              >
                <Card className="gap-0 overflow-hidden py-0 shadow-none">
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4">
                    <div>
                      <h2 className="text-sm font-semibold">Student records</h2>
                      <p className="mt-1 text-xs text-muted-foreground">
                        Recognized identities and saved attendance.
                      </p>
                    </div>
                    <TabsList aria-label="Record filter">
                      <TabsTrigger value="all">All records</TabsTrigger>
                      <TabsTrigger value="present">Present only</TabsTrigger>
                    </TabsList>
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
                    <div className="relative w-full sm:max-w-xs">
                      <Search className="pointer-events-none absolute left-2.5 top-2.5 size-3.5 text-muted-foreground" />
                      <Input
                        ref={recordSearch}
                        aria-label="Search students"
                        placeholder="Search name, index or department…"
                        value={query}
                        onChange={(event) => setQuery(event.target.value)}
                        className="h-8 pl-8 text-xs shadow-none"
                      />
                    </div>
                    <div className="flex items-center gap-3">
                      {checked.length > 0 && (
                        <>
                          <span className="text-xs text-muted-foreground">
                            {checked.length} selected
                          </span>
                          <Button
                            size="xs"
                            variant="outline"
                            disabled={
                              !!error ||
                              !feed?.attendance.some((record) =>
                                checked.includes(record.student_no),
                              )
                            }
                            onClick={() => exportAttendance(true)}
                          >
                            Export selected
                          </Button>
                          <Button
                            size="xs"
                            variant="ghost"
                            onClick={() => setChecked([])}
                          >
                            Clear
                          </Button>
                        </>
                      )}
                      <span className="text-xs text-muted-foreground">
                        {students.length} record
                        {students.length === 1 ? "" : "s"}
                      </span>
                    </div>
                  </div>
                  {["all", "present"].map((value) => (
                    <TabsContent key={value} value={value} className="m-0">
                      <Table className="min-w-[650px]">
                        <TableHeader className="bg-muted/35">
                          <TableRow>
                            <TableHead className="w-10">
                              <input
                                type="checkbox"
                                aria-label="Select all visible students"
                                disabled={!students.length}
                                checked={
                                  !!students.length &&
                                  students.every((student) =>
                                    checked.includes(student.student_no),
                                  )
                                }
                                onChange={(event) =>
                                  setChecked(
                                    event.target.checked
                                      ? [
                                          ...new Set([
                                            ...checked,
                                            ...students.map(
                                              (student) => student.student_no,
                                            ),
                                          ]),
                                        ]
                                      : checked.filter(
                                          (id) =>
                                            !students.some(
                                              (student) =>
                                                student.student_no === id,
                                            ),
                                        ),
                                  )
                                }
                              />
                            </TableHead>
                            <TableHead>Student</TableHead>
                            <TableHead>Index number</TableHead>
                            <TableHead>Academic details</TableHead>
                            <TableHead>Recorded</TableHead>
                            <TableHead>Status</TableHead>
                            <TableHead className="w-10">
                              <span className="sr-only">Details</span>
                            </TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {students.map((student) => {
                            const details = academic(student);
                            const record = feed?.attendance.find(
                              (r) => r.student_no === student.student_no,
                            );
                            return (
                              <TableRow
                                key={student.student_no}
                                data-state={
                                  checked.includes(student.student_no)
                                    ? "selected"
                                    : undefined
                                }
                              >
                                <TableCell>
                                  <input
                                    type="checkbox"
                                    aria-label={`Select ${student.full_name}`}
                                    checked={checked.includes(
                                      student.student_no,
                                    )}
                                    onChange={(event) =>
                                      setChecked(
                                        event.target.checked
                                          ? [...checked, student.student_no]
                                          : checked.filter(
                                              (id) => id !== student.student_no,
                                            ),
                                      )
                                    }
                                  />
                                </TableCell>
                                <TableCell>
                                  <button
                                    onClick={() => setSelected(student)}
                                    className="flex items-center gap-2.5 text-left"
                                  >
                                    <Avatar name={student.full_name} />
                                    <span className="min-w-[100px] text-xs font-medium">
                                      {student.full_name}
                                    </span>
                                  </button>
                                </TableCell>
                                <TableCell className="whitespace-nowrap font-mono text-[11px] text-muted-foreground">
                                  {student.student_no}
                                </TableCell>
                                <TableCell>
                                  <p className="text-xs font-medium">
                                    {details.level
                                      ? `Level ${details.level}`
                                      : "Level not supplied"}
                                  </p>
                                  <p className="mt-1 max-w-[190px] text-[11px] leading-4 text-muted-foreground">
                                    {details.department ||
                                      details.programme ||
                                      "Department not supplied"}
                                  </p>
                                </TableCell>
                                <TableCell className="whitespace-nowrap font-mono text-[11px] text-muted-foreground">
                                  {time(record?.recorded_at)}
                                </TableCell>
                                <TableCell>
                                  <AttendanceBadge present={!!record} />
                                </TableCell>
                                <TableCell className="px-2">
                                  <Button
                                    variant="ghost"
                                    size="icon-xs"
                                    onClick={() => setSelected(student)}
                                    aria-label={`View ${student.full_name}`}
                                  >
                                    <ArrowUpRight className="size-3.5" />
                                  </Button>
                                </TableCell>
                              </TableRow>
                            );
                          })}
                          {!students.length && (
                            <TableRow>
                              <TableCell
                                colSpan={7}
                                className="h-52 text-center"
                              >
                                <p className="text-sm font-medium">
                                  {loading
                                    ? "Loading records…"
                                    : query
                                      ? "No matching students"
                                      : tab === "present"
                                        ? "No attendance recorded"
                                        : "No recognition records yet"}
                                </p>
                                <p className="mx-auto mt-2 max-w-xs text-xs leading-5 text-muted-foreground">
                                  {query
                                    ? "Try a different name, index number or department."
                                    : error
                                      ? "Reconnect the local API to load records."
                                      : "Use Demo controls to start recognition. Confirmed identities will appear here."}
                                </p>
                              </TableCell>
                            </TableRow>
                          )}
                        </TableBody>
                      </Table>
                    </TabsContent>
                  ))}
                  <div className="flex flex-wrap items-center justify-between gap-2 border-t bg-muted/20 px-4 py-3 text-[10px] text-muted-foreground">
                    <span>Academic labels are presentation metadata.</span>
                    <span className="font-mono">24 → Level 300</span>
                  </div>
                </Card>
              </Tabs>
            </section>
            <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              <Card className="gap-0 py-0 shadow-none">
                <div className="flex items-center justify-between border-b px-4 py-3.5">
                  <h2 className="text-xs font-semibold">
                    Latest student record
                  </h2>
                  <Users className="size-3.5 text-muted-foreground" />
                </div>
                <CardContent className="p-4">
                  {latestStudent && latestAcademic ? (
                    <>
                      <div className="flex items-center gap-3">
                        <Avatar name={latestStudent.full_name} large />
                        <div className="min-w-0">
                          <button
                            onClick={() => setSelected(latestStudent)}
                            className="text-left text-sm font-medium hover:underline"
                          >
                            {latestStudent.full_name}
                          </button>
                          <p className="mt-1 break-all font-mono text-[10px] text-muted-foreground">
                            {latestStudent.student_no}
                          </p>
                        </div>
                      </div>
                      <dl className="mt-5 space-y-3 text-xs">
                        <div className="flex justify-between gap-3">
                          <dt className="text-muted-foreground">Level</dt>
                          <dd className="font-medium">
                            {latestAcademic.level
                              ? `Level ${latestAcademic.level}`
                              : "Not supplied"}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">Department</dt>
                          <dd className="mt-1 leading-5">
                            {latestAcademic.department || "Not supplied"}
                          </dd>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <dt className="text-muted-foreground">Attendance</dt>
                          <dd>
                            <AttendanceBadge present={!!lastRecord} />
                          </dd>
                        </div>
                      </dl>
                      <Button
                        variant="outline"
                        size="sm"
                        className="mt-5 w-full text-xs"
                        onClick={() => setSelected(latestStudent)}
                      >
                        Open student details
                        <ArrowUpRight />
                      </Button>
                    </>
                  ) : (
                    <p className="py-5 text-xs leading-5 text-muted-foreground">
                      Student information appears after recognition or when
                      saved attendance is loaded.
                    </p>
                  )}
                </CardContent>
              </Card>
              <Card
                id="activity"
                className="gap-0 overflow-hidden py-0 shadow-none"
              >
                <div className="flex items-center justify-between border-b px-4 py-3.5">
                  <h2 className="text-xs font-semibold">Activity log</h2>
                  <Badge
                    variant="secondary"
                    className="rounded-md font-mono text-[10px]"
                  >
                    {live?.events.length || 0}
                  </Badge>
                </div>
                <CardContent className="max-h-[440px] overflow-y-auto p-0">
                  {live?.events.length ? (
                    [...live.events]
                      .reverse()
                      .slice(0, 30)
                      .map((event) => (
                        <div
                          key={event.id}
                          className="flex gap-2.5 border-b px-4 py-3 last:border-0"
                        >
                          <span
                            className={`mt-1.5 size-1.5 shrink-0 rounded-full ${["present", "already_present"].includes(event.kind) ? "bg-emerald-600" : ["unknown", "not_eligible", "error", "not_live"].includes(event.kind) ? "bg-amber-500" : "bg-neutral-400"}`}
                          />
                          <div className="min-w-0 flex-1">
                            <div className="flex items-start justify-between gap-2">
                              <p className="min-w-0 break-words text-[11px] font-medium">
                                {nameFor(event.student_no) ||
                                  (event.track_id != null
                                    ? `Face track #${event.track_id}`
                                    : "Camera session")}
                              </p>
                              <time className="shrink-0 font-mono text-[9px] leading-4 text-muted-foreground">
                                {time(event.at)}
                              </time>
                            </div>
                            <p className="mt-1 text-[11px] text-muted-foreground">
                              {eventLabel(event.kind)}
                            </p>
                            {!!event.reasons?.length && (
                              <p className="mt-1 text-[10px] leading-4 text-amber-800">
                                {event.reasons.join(" · ")}
                              </p>
                            )}
                          </div>
                        </div>
                      ))
                  ) : (
                    <p className="px-4 py-8 text-xs leading-5 text-muted-foreground">
                      No events yet. Recognition activity appears here when the
                      camera session starts.
                    </p>
                  )}
                </CardContent>
                <div className="border-t bg-muted/25 px-4 py-2.5 text-[10px] text-muted-foreground">
                  {active
                    ? "Recognition engine running"
                    : "Recognition engine on standby"}
                </div>
              </Card>
            </div>
          </div>
          <footer className="palette-footer flex flex-wrap items-center justify-between gap-2 border-t pt-4 text-[10px] text-muted-foreground">
            <span>InsightFace / ByteTrack · Local processing</span>
            <span>
              {illustration
                ? "Illustrative data only"
                : error
                  ? "Connection interrupted"
                  : live?.updated_at
                    ? `Updated ${time(live.updated_at)} GMT · refreshes every 2s`
                    : "Waiting for local session"}
            </span>
          </footer>
        </main>
      </div>
      <Dialog
        open={!!selected}
        onOpenChange={(open) => !open && setSelected(null)}
      >
        <DialogContent>
          <DialogTitle className="text-lg font-semibold tracking-tight">
            Student details
          </DialogTitle>
          <DialogDescription className="mt-2 text-xs leading-5 text-muted-foreground">
            Enrollment identity and examination attendance. Academic details are
            locally supplied, not university-verified.
          </DialogDescription>
          {selected && (
            <>
              <div className="mt-7 flex items-center gap-3 border-y py-5">
                <Avatar name={selected.full_name} large />
                <div className="min-w-0">
                  <p className="text-base font-semibold">
                    {selected.full_name}
                  </p>
                  <p className="mt-1 break-all font-mono text-xs text-muted-foreground">
                    {selected.student_no}
                  </p>
                </div>
              </div>
              <div className="mt-5 flex items-center justify-between">
                <Badge variant="secondary" className="rounded-md">
                  {selectedAcademic?.level
                    ? `Level ${selectedAcademic.level}`
                    : "Level not supplied"}
                </Badge>
                <AttendanceBadge present={!!selectedRecord} />
              </div>
              <dl className="mt-5 divide-y">
                {[
                  ["Programme", selectedAcademic?.programme || "Not supplied"],
                  [
                    "Department",
                    selectedAcademic?.department || "Not supplied",
                  ],
                  [
                    "Index programme code",
                    selectedAcademic?.index_programme_code || "Not supplied",
                  ],
                  [
                    "Index year code",
                    selectedAcademic?.index_year_code || "Not supplied",
                  ],
                  [
                    live?.demo_classroom
                      ? "Attendance record scope"
                      : "Examination",
                    exam?.course_title || "—",
                  ],
                  ["Building / venue", exam?.hall || "—"],
                  ["Recognized at", time(selectedRecognition?.at)],
                  ["Attendance recorded", time(selectedRecord?.recorded_at)],
                  ["Face samples", selected.face_samples],
                  ["Source", selectedRecord?.source || "Not recorded"],
                ].map(([label, value]) => (
                  <div
                    key={String(label)}
                    className="flex justify-between gap-5 py-3 text-xs"
                  >
                    <dt className="shrink-0 text-muted-foreground">{label}</dt>
                    <dd className="text-right font-medium leading-5">
                      {value}
                    </dd>
                  </div>
                ))}
              </dl>
              {selectedAcademic?.is_demo_metadata && (
                <div className="mt-5 rounded-md border bg-muted/40 p-3 text-[11px] leading-5 text-muted-foreground">
                  <p className="font-medium text-foreground">
                    Academic display rules
                  </p>
                  <p className="mt-1">
                    CSC → Computer Science and Information Technology.
                    <br />
                    24 → Level 300 for this demonstration.
                  </p>
                  <p className="mt-2">
                    These rules do not change student records or eligibility.
                  </p>
                </div>
              )}
              <p className="mt-4 text-[10px] text-muted-foreground">
                Initials placeholder · no portrait available in this view.
              </p>
            </>
          )}
        </DialogContent>
      </Dialog>
      <Dialog open={help} onOpenChange={setHelp}>
        <DialogContent>
          <DialogTitle className="text-lg font-semibold">
            Your local demonstration
          </DialogTitle>
          <DialogDescription className="mt-2 text-xs leading-5 text-muted-foreground">
            Use Demo controls to operate recognition, sync submissions and
            prepare volunteers. The camera window runs on your PC.
          </DialogDescription>
          <ol className="mt-7 space-y-6 text-sm leading-6">
            <li>
              <strong className="font-medium">1. Launch the workspace</strong>
              <p className="mt-2 text-xs text-muted-foreground">
                Double-click Start Demo.cmd. It opens the API and dashboard.
                Manual API fallback:
              </p>
              <code className="mt-2 block break-all rounded-md border bg-muted/40 p-3 text-[11px]">
                uv run --frozen --extra vision uvicorn app.main:app --host
                127.0.0.1 --port 8000
              </code>
            </li>
            <li>
              <strong className="font-medium">
                2. Prepare and start recognition
              </strong>
              <p className="mt-2 text-xs text-muted-foreground">
                In Demo controls, select the exam, sync submissions and start
                recognition. Stop the camera before changing the gallery. Manual
                camera fallback:
              </p>
              <code className="mt-2 block break-all rounded-md border bg-muted/40 p-3 text-[11px]">
                uv run --frozen --extra vision python -m app.vision.attend
                --exam CS101 --det-size 480 --threads 4
              </code>
            </li>
            <li className="text-xs text-muted-foreground">
              Run commands from the same backend folder. Keep the API and
              dashboard local; there is no authentication for public hosting.
            </li>
          </ol>
          <div className="mt-7 border-t pt-4 text-xs leading-5 text-muted-foreground">
            “Identified” counts distinct session identities. “Present” includes
            saved records from previous runs of the exam. Unidentified tracks
            are not unique people. Academic index labels are presentation
            metadata.
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
