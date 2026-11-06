import { academic, type Attendance, type Student } from "./data";

export function attendanceCharts(records: Attendance[], students: Student[]) {
  const unique = new Map<string, Attendance>();
  const stamp = (at: string) =>
    Date.parse(/Z$|[+-]\d\d:\d\d$/.test(at) ? at : `${at}Z`);
  let invalidDates = 0;
  // Attendance is per student per exam. Keep the earliest saved record if a duplicate appears.
  for (const record of records) {
    const previous = unique.get(record.student_no);
    if (
      !previous ||
      !Number.isFinite(stamp(previous.recorded_at)) ||
      stamp(record.recorded_at) < stamp(previous.recorded_at)
    )
      unique.set(record.student_no, record);
  }
  const minutes = new Map<number, number>();
  const levels = new Map<string, number>();
  const roster = new Map(
    students.map((student) => [student.student_no, student]),
  );
  for (const record of unique.values()) {
    const at = stamp(record.recorded_at);
    if (Number.isFinite(at)) {
      const minute = Math.floor(at / 60000) * 60000;
      minutes.set(minute, (minutes.get(minute) || 0) + 1);
    } else invalidDates++;
    const student = roster.get(record.student_no);
    const level = student ? academic(student).level : null;
    const label = level ? `Level ${level}` : "Not supplied";
    levels.set(label, (levels.get(label) || 0) + 1);
  }
  let cumulative = 0;
  const timeline = [...minutes]
    .sort(([a], [b]) => a - b)
    .map(([at, count]) => ({ at, count: (cumulative += count) }));
  return {
    timeline,
    levels: [...levels]
      .sort(([a], [b]) => a.localeCompare(b, undefined, { numeric: true }))
      .map(([level, count]) => ({ level, count })),
    total: unique.size,
    invalidDates,
  };
}

export function chartTime(at: number) {
  return new Date(at).toLocaleTimeString("en-GB", {
    timeZone: "Africa/Accra",
    hour: "2-digit",
    minute: "2-digit",
  });
}
export function chartDate(at: number) {
  return (
    new Date(at).toLocaleString("en-GB", {
      timeZone: "Africa/Accra",
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }) + " GMT"
  );
}
