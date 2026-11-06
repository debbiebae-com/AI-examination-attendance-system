import { describe, expect, it } from "vitest";
import { attendanceCharts, chartTime } from "./charts";
import { demoFeed } from "./demo";
describe("saved attendance chart data", () => {
  it("uses saved records only, in cumulative UTC minute buckets", () => {
    const feed = demoFeed();
    const data = attendanceCharts(feed.attendance, feed.students);
    expect(data.timeline.map((point) => point.count)).toEqual([1, 2, 3, 4]);
    expect(data.levels).toEqual([{ level: "Level 300", count: 4 }]);
    expect(chartTime(Date.parse("2026-11-06T10:30:00Z"))).toBe("10:30");
  });
  it("handles unsorted duplicates, invalid dates and missing student metadata", () => {
    const row = demoFeed().attendance[0];
    const data = attendanceCharts(
      [
        { ...row, recorded_at: "2026-11-06T10:03:00" },
        { ...row, recorded_at: "2026-11-06T10:01:00Z" },
        { ...row, student_no: "MISSING", recorded_at: "invalid" },
      ],
      [],
    );
    expect(data.total).toBe(2);
    expect(data.invalidDates).toBe(1);
    expect(data.timeline).toEqual([
      { at: Date.parse("2026-11-06T10:01:00Z"), count: 1 },
    ]);
    expect(data.levels).toEqual([{ level: "Not supplied", count: 2 }]);
  });
  it("has no fake baseline, attendance or inferred absent counts", () => {
    expect(attendanceCharts([], demoFeed().students)).toEqual({
      timeline: [],
      levels: [],
      total: 0,
      invalidDates: 0,
    });
  });
});
