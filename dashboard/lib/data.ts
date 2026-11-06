export type AcademicDisplay = {
  department: string | null;
  programme: string | null;
  level: number | null;
  index_programme_code: string | null;
  index_year_code: string | null;
  department_source: string;
  level_source: string;
  is_demo_metadata: boolean;
};
export type Exam = {
  id: number;
  course_code: string;
  course_title: string;
  hall: string;
  starts_at: string;
  ends_at: string;
};
export type Student = {
  student_no: string;
  full_name: string;
  programme: string;
  level: number;
  has_photo: boolean;
  face_samples: number;
  presentation?: AcademicDisplay;
};
export type Attendance = {
  student_no: string;
  full_name: string;
  recorded_at: string;
  confidence: number | null;
  source: string;
};
export type LiveEvent = {
  id: number;
  at: string;
  kind: string;
  track_id?: number | null;
  student_no?: string | null;
  reasons?: string[];
  similarity?: number;
};
export type Session = {
  demo_mode?: boolean;
  demo_classroom?: boolean;
  classroom_name?: string | null;
  camera_source?: "pc" | "droidcam";
  camera_index?: number;
  camera_backend?: string;
  session_id: string | null;
  status: string;
  exam?: Exam | null;
  started_at?: string;
  updated_at?: string;
  error?: string | null;
  identified_count?: number;
  unidentified_now: number;
  visible_faces?: number;
  processed_fps?: number;
  processing_ms?: number;
  present_count: number;
  events: LiveEvent[];
};
export type Feed = {
  session: Session;
  students: Student[];
  attendance: Attendance[];
};
export const time = (value?: string) =>
  value
    ? new Date(
        value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value)
          ? value
          : `${value}Z`,
      ).toLocaleTimeString("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        timeZone: "Africa/Accra",
      })
    : "—";
export const initials = (name: string) =>
  name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((n) => n[0])
    .join("");
export const statusLabel = (status: string) =>
  ({
    running: "Camera active",
    starting: "Starting camera",
    stopped: "Session stopped",
    idle: "No active session",
    error: "Camera error",
    disconnected: "Worker disconnected",
  })[status] || status;
export const eventLabel = (kind: string) =>
  ({
    identified: "Identity confirmed",
    present: "Attendance recorded",
    already_present: "Already marked present",
    unknown: "Unidentified face detected",
    no_embedding: "Face sample unusable",
    checking: "Verifying identity",
    not_live: "Liveness check failed",
    not_eligible: "Attendance not recorded",
    stopped: "Session stopped",
    error: "Recognition worker error",
  })[kind] || kind;
export function csv(records: Attendance[], exam?: Exam | null) {
  const cell = (value: unknown) =>
    '"' +
    String(value ?? "")
      .replace(/^[\s]*[=+@-]/, (match) => "'" + match)
      .replaceAll('"', '""') +
    '"';
  return [
    [
      "Name",
      "Index number",
      "Examination",
      "Recorded at (UTC)",
      "Source",
      "Similarity (not probability)",
    ],
    ...records.map((r) => [
      r.full_name,
      r.student_no,
      exam?.course_code ?? "",
      r.recorded_at,
      r.source,
      r.confidence,
    ]),
  ]
    .map((row) => row.map(cell).join(","))
    .join("\r\n");
}
export function visibleStudents(feed: Feed, query: string) {
  const known = new Set([
    ...feed.attendance.map((r) => r.student_no),
    ...feed.session.events
      .filter((e) => e.kind === "identified")
      .map((e) => e.student_no),
  ]);
  const recent = (id: string) =>
    feed.session.events.filter((e) => e.student_no === id).at(-1)?.at ||
    feed.attendance.find((r) => r.student_no === id)?.recorded_at ||
    "";
  return feed.students
    .filter(
      (s) =>
        known.has(s.student_no) &&
        `${s.full_name} ${s.student_no} ${s.programme} ${academic(s).department || ""} ${academic(s).level || ""}`
          .toLowerCase()
          .includes(query.toLowerCase()),
    )
    .sort((a, b) => recent(b.student_no).localeCompare(recent(a.student_no)));
}

// Display-only compatibility rules also apply to older/stale API responses.
// Keep in step with backend/app/presentation.py; never infer other year levels.
export function academic(student: Student): AcademicDisplay {
  const base: AcademicDisplay = student.presentation || {
    department: null,
    programme: student.programme,
    level: student.level,
    index_programme_code: null,
    index_year_code: null,
    department_source: "not_supplied",
    level_source: "local_record",
    is_demo_metadata: false,
  };
  const match = /^[A-Z]+\/([A-Z]+)\/([0-9]{2})\/[0-9]+$/i.exec(
    student.student_no.trim(),
  );
  if (!match) return base;
  const code = match[1].toUpperCase(),
    year = match[2];
  return {
    ...base,
    index_programme_code: code,
    index_year_code: year,
    ...(code === "CSC"
      ? {
          department: "Computer Science and Information Technology",
          department_source: "demo_index_rule",
        }
      : {}),
    ...(year === "24" ? { level: 300, level_source: "demo_index_rule" } : {}),
    is_demo_metadata: base.is_demo_metadata || code === "CSC" || year === "24",
  };
}
