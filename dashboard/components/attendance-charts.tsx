"use client";

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card } from "@/components/ui/card";
import { attendanceCharts, chartDate, chartTime } from "@/lib/charts";
import type { Feed } from "@/lib/data";

export function AttendanceCharts({
  feed,
  offline,
  illustration,
}: {
  feed: Feed | null;
  offline: boolean;
  illustration: boolean;
}) {
  const data = useMemo(
    () => attendanceCharts(feed?.attendance || [], feed?.students || []),
    [feed],
  );
  const empty = offline
    ? "Charts unavailable while the local API is disconnected."
    : !feed
      ? "Waiting for examination data."
      : "No saved attendance for this examination yet.";
  const ready = !!feed && !offline && data.total > 0;
  return (
    <section
      aria-label="Attendance charts"
      className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]"
    >
      <Card className="chart-card min-w-0 gap-0 overflow-hidden py-0 shadow-none">
        <div className="chart-heading border-b px-5 py-4">
          <h2 className="text-sm font-semibold">Attendance over time</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Cumulative saved records · GMT ·{" "}
            {illustration ? "illustrative data" : "selected examination"}
          </p>
        </div>
        <div className="p-4">
          {ready && data.timeline.length ? (
            <>
              <div
                className="h-56 w-full min-w-0"
                role="img"
                aria-label={`Cumulative attendance: ${data.timeline.at(-1)?.count} saved records across ${data.timeline.length} recorded minute buckets.`}
              >
                <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                  <AreaChart
                    data={data.timeline}
                    margin={{ top: 12, right: 14, left: -18, bottom: 0 }}
                    accessibilityLayer
                  >
                    <CartesianGrid
                      vertical={false}
                      stroke="#d5e6e2"
                      strokeDasharray="3 4"
                    />
                    <XAxis
                      dataKey="at"
                      type="number"
                      domain={["dataMin", "dataMax"]}
                      tickFormatter={chartTime}
                      tick={{ fontSize: 11, fill: "#48656b" }}
                      axisLine={false}
                      tickLine={false}
                      minTickGap={40}
                    />
                    <YAxis
                      allowDecimals={false}
                      domain={[0, "auto"]}
                      tick={{ fontSize: 11, fill: "#48656b" }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip
                      labelFormatter={(value) => chartDate(Number(value))}
                      contentStyle={{
                        borderRadius: 8,
                        borderColor: "#98d8d0",
                        color: "#04222b",
                      }}
                      formatter={(value) => [value, "Saved attendance"]}
                    />
                    <Area
                      name="Saved attendance"
                      dataKey="count"
                      type="stepAfter"
                      stroke="#10606f"
                      fill="#4fb8b4"
                      fillOpacity={0.4}
                      strokeWidth={3}
                      dot={{
                        r: 4,
                        fill: "#10606f",
                        stroke: "#fff",
                        strokeWidth: 2,
                      }}
                      activeDot={{ r: 6 }}
                      isAnimationActive={false}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              <details className="mt-3 text-xs text-muted-foreground">
                <summary className="cursor-pointer">View chart values</summary>
                <ul className="mt-2 max-h-32 space-y-1 overflow-auto">
                  {data.timeline.map((point) => (
                    <li key={point.at}>
                      {chartDate(point.at)}: {point.count} saved
                    </li>
                  ))}
                </ul>
              </details>
            </>
          ) : (
            <p className="flex h-56 items-center justify-center text-center text-xs text-muted-foreground">
              {ready
                ? "Saved records have no valid timestamps to plot."
                : empty}
            </p>
          )}
          {!!data.invalidDates && !offline && (
            <p className="mt-2 text-xs text-amber-800">
              {data.invalidDates} record(s) omitted from the time chart because
              their timestamp is invalid.
            </p>
          )}
        </div>
      </Card>
      <Card className="chart-card min-w-0 gap-0 overflow-hidden py-0 shadow-none">
        <div className="chart-heading border-b px-5 py-4">
          <h2 className="text-sm font-semibold">Attendance by level</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Marked-present students · presentation level labels
          </p>
        </div>
        <div className="p-4">
          {ready ? (
            <>
              <div
                className="h-56 w-full min-w-0"
                role="img"
                aria-label={`Saved attendance by level: ${data.levels.map((item) => `${item.level}: ${item.count}`).join(", ")}.`}
              >
                <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                  <BarChart
                    data={data.levels}
                    layout="vertical"
                    margin={{ top: 12, right: 16, left: 0, bottom: 0 }}
                    accessibilityLayer
                  >
                    <CartesianGrid
                      horizontal={false}
                      stroke="#d5e6e2"
                      strokeDasharray="3 4"
                    />
                    <XAxis
                      type="number"
                      allowDecimals={false}
                      tick={{ fontSize: 11, fill: "#48656b" }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      type="category"
                      dataKey="level"
                      width={90}
                      tick={{ fontSize: 11, fill: "#0a3d4a" }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip
                      cursor={{ fill: "#e2f4f0" }}
                      contentStyle={{
                        borderRadius: 8,
                        borderColor: "#98d8d0",
                        color: "#04222b",
                      }}
                      formatter={(value) => [value, "Saved attendance"]}
                    />
                    <Bar
                      name="Saved attendance"
                      dataKey="count"
                      fill="#1d8b94"
                      radius={[0, 5, 5, 0]}
                      maxBarSize={38}
                      isAnimationActive={false}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-3 text-xs text-muted-foreground">
                {data.total} saved record{data.total === 1 ? "" : "s"}. Not a
                count of all enrolled or absent students.
              </p>
            </>
          ) : (
            <p className="flex h-56 items-center justify-center text-center text-xs text-muted-foreground">
              {empty}
            </p>
          )}
        </div>
      </Card>
    </section>
  );
}
