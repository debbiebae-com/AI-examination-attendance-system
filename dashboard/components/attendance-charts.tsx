"use client";

import { useMemo } from "react";
import {
  Legend,
  ReferenceLine,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Sparkles } from "lucide-react";
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
  const grouped = data.timeline.map((point, index) => ({
    ...point,
    newCount: point.count - (data.timeline[index - 1]?.count || 0),
  }));
  const ready = !!feed && !offline && data.total > 0;
  return (
    <section
      aria-label="Attendance charts"
      className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]"
    >
      <Card className="chart-card min-w-0 gap-0 overflow-hidden py-0 shadow-none">
        <div className="chart-heading border-b px-5 py-4">
          <h2 className="text-sm font-semibold">Attendance over time</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Cumulative saved records · GMT ·{" "}
            {illustration
              ? "illustrative data"
              : feed?.session.demo_classroom
                ? "Demonstration records"
                : "selected examination"}
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
                  <BarChart
                    data={grouped}
                    margin={{ top: 12, right: 14, left: -18, bottom: 0 }}
                    accessibilityLayer
                  >
                    <CartesianGrid
                      vertical={false}
                      stroke="#353535"
                      strokeDasharray="3 4"
                    />
                    <XAxis
                      dataKey="at"
                      type="category"
                      tickFormatter={chartTime}
                      tick={{ fontSize: 11, fill: "#9ca3af" }}
                      axisLine={false}
                      tickLine={false}
                      minTickGap={40}
                    />
                    <YAxis
                      allowDecimals={false}
                      domain={[0, "auto"]}
                      tick={{ fontSize: 11, fill: "#9ca3af" }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip
                      labelFormatter={(value) => chartDate(Number(value))}
                      contentStyle={{
                        borderRadius: 8,
                        borderColor: "#3a3a3a",
                        backgroundColor: "#2a2a2a",
                        color: "#f5f5f5",
                      }}
                      formatter={(value, name) => [value, name]}
                    />
                    <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
                    <ReferenceLine
                      x={data.timeline.at(-1)?.at}
                      stroke="#e8822a"
                      strokeDasharray="4 4"
                      label={{
                        value: "Latest record",
                        fill: "#ffb16e",
                        fontSize: 10,
                        position: "insideTopRight",
                      }}
                    />
                    <Bar
                      name="Cumulative saved"
                      dataKey="count"
                      fill="#e8822a"
                      fillOpacity={0.35}
                      radius={[3, 3, 0, 0]}
                      maxBarSize={30}
                      isAnimationActive={false}
                    />
                    <Bar
                      name="New in minute"
                      dataKey="newCount"
                      fill="#e8822a"
                      radius={[3, 3, 0, 0]}
                      maxBarSize={30}
                      isAnimationActive={false}
                    />
                  </BarChart>
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
          {ready && (
            <div className="mb-3 flex items-center gap-2 rounded-lg border border-input bg-muted px-3 py-2.5 text-xs text-muted-foreground">
              <Sparkles className="size-4 shrink-0 text-primary" />
              {data.total} saved · {data.levels.length} display-level group
              {data.levels.length === 1 ? "" : "s"}. Based on records, not an AI
              prediction.
            </div>
          )}
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
                      stroke="#353535"
                      strokeDasharray="3 4"
                    />
                    <XAxis
                      type="number"
                      allowDecimals={false}
                      tick={{ fontSize: 11, fill: "#9ca3af" }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      type="category"
                      dataKey="level"
                      width={90}
                      tick={{ fontSize: 11, fill: "#9ca3af" }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip
                      cursor={{ fill: "#e8822a15" }}
                      contentStyle={{
                        borderRadius: 8,
                        borderColor: "#3a3a3a",
                        backgroundColor: "#2a2a2a",
                        color: "#f5f5f5",
                      }}
                      formatter={(value) => [value, "Saved attendance"]}
                    />
                    <Bar
                      name="Saved attendance"
                      dataKey="count"
                      fill="#e8822a"
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
