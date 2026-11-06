import React from "react";
import { render, screen } from "@testing-library/react";
import { it, expect } from "vitest";
import { AttendanceCharts } from "@/components/attendance-charts";
import { demoFeed } from "@/lib/demo";
it("has honest empty states without fabricated chart data", () => {
  const feed = demoFeed();
  feed.attendance = [];
  render(<AttendanceCharts feed={feed} offline={false} illustration={false} />);
  expect(
    screen.getAllByText("No saved attendance for this examination yet."),
  ).toHaveLength(2);
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});
it("hides retained chart values on disconnection", () => {
  render(<AttendanceCharts feed={demoFeed()} offline illustration={false} />);
  expect(
    screen.getAllByText(
      "Charts unavailable while the local API is disconnected.",
    ),
  ).toHaveLength(2);
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});
