import React from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { Dashboard } from "@/components/dashboard";
import { demoFeed } from "@/lib/demo";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) => ({
      ok: true,
      json: async () =>
        path.includes("students")
          ? []
          : {
              session_id: null,
              status: "idle",
              events: [],
              unidentified_now: 0,
              present_count: 0,
            },
    })),
  );
});
it("shows real idle state, not fabricated students or a running camera", async () => {
  render(<Dashboard />);
  expect(await screen.findByText("No active session")).toBeInTheDocument();
  expect(screen.queryByText("Kwame Mensah")).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Export attendance" }),
  ).toBeDisabled();
});
it("offers an explicit illustration, search, student details and exit", async () => {
  const user = userEvent.setup();
  render(<Dashboard />);
  await screen.findByText("No active session");
  await user.click(screen.getByRole("button", { name: "Preview layout" }));
  expect(screen.getByText("Illustrative preview.")).toBeInTheDocument();
  await user.type(
    screen.getByRole("textbox", { name: "Search students" }),
    "PS/CSC/24/0016",
  );
  expect(screen.getAllByRole("row")).toHaveLength(2);
  await user.click(screen.getByRole("button", { name: "View Kwame Mensah" }));
  const panel = screen.getByRole("dialog");
  expect(within(panel).getByText("PS/CSC/24/0016")).toBeInTheDocument();
  expect(
    within(panel).getByText("Computer Science and Information Technology"),
  ).toBeInTheDocument();
  expect(within(panel).getByText("Level 300")).toBeInTheDocument();
  expect(
    within(panel).getByText(/These rules do not change student records/),
  ).toBeInTheDocument();
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Exit preview" }));
  await screen.findByText("No active session");
  expect(screen.queryByText("Illustrative preview.")).not.toBeInTheDocument();
});
it("shows a disconnected alert when the local API is unavailable", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: false, status: 503 })),
  );
  render(<Dashboard />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Local API is offline",
  );
  expect(screen.getByText("API disconnected")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Export attendance" }),
  ).toBeDisabled();
});
it("renders actual API records and differentiates identity from attendance", async () => {
  const fixture = demoFeed();
  fixture.session.session_id = "live-test";
  fixture.attendance.pop();
  fixture.session.present_count = 3;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) => ({
      ok: true,
      json: async () =>
        path.includes("live/session")
          ? fixture.session
          : path.includes("students")
            ? fixture.students
            : fixture.attendance,
    })),
  );
  render(<Dashboard />);
  await screen.findByText("Camera active");
  expect(screen.getByText("Not recorded")).toBeInTheDocument();
  expect(screen.getAllByRole("row")).toHaveLength(5);
  expect(screen.queryByText("Illustrative preview.")).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Export attendance" }),
  ).toBeEnabled();
});

it("renders level 300 for CSC/24 with an older API in the table and profile", async () => {
  const fixture = demoFeed();
  fixture.session.session_id = "older-api";
  fixture.students = fixture.students.map((student) => ({
    ...student,
    presentation: undefined,
    level: 100,
  }));
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) => ({
      ok: true,
      json: async () =>
        path.includes("live/session")
          ? fixture.session
          : path.includes("students")
            ? fixture.students
            : fixture.attendance,
    })),
  );
  const user = userEvent.setup();
  render(<Dashboard />);
  const index = await screen.findByText("PS/CSC/24/0016", { selector: "td" });
  expect(
    within(index.closest("tr")!).getByText("Level 300"),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "View Kwame Mensah" }));
  expect(
    within(screen.getByRole("dialog")).getByText("Level 300"),
  ).toBeInTheDocument();
});
it("filters saved attendance with keyboard-accessible shadcn tabs", async () => {
  const fixture = demoFeed();
  fixture.attendance.pop();
  fixture.session.present_count = 3;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) => ({
      ok: true,
      json: async () =>
        path.includes("live/session")
          ? fixture.session
          : path.includes("students")
            ? fixture.students
            : fixture.attendance,
    })),
  );
  const user = userEvent.setup();
  render(<Dashboard />);
  await screen.findByText("Camera active");
  expect(screen.getAllByRole("row")).toHaveLength(5);
  await user.click(screen.getByRole("tab", { name: "Present only" }));
  expect(screen.getByRole("tab", { name: "Present only" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  expect(screen.getAllByRole("row")).toHaveLength(4);
  await user.keyboard("{ArrowLeft}");
  expect(screen.getByRole("tab", { name: "All records" })).toHaveFocus();
  expect(screen.getAllByRole("row")).toHaveLength(5);
});
it("opens and closes the compact navigation", async () => {
  const user = userEvent.setup();
  render(<Dashboard />);
  await screen.findByText("No active session");
  const toggle = screen.getByRole("button", { name: "Toggle navigation" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  await user.click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  await user.click(screen.getByRole("link", { name: "Activity log" }));
  expect(toggle).toHaveAttribute("aria-expanded", "false");
});

it("supports Ctrl+K and shared workspace search without fake notifications", async () => {
  const scroll = Object.getOwnPropertyDescriptor(
    Element.prototype,
    "scrollIntoView",
  );
  Object.defineProperty(Element.prototype, "scrollIntoView", {
    configurable: true,
    value: vi.fn(),
  });
  try {
    const user = userEvent.setup();
    render(<Dashboard />);
    await screen.findByText("No active session");
    await user.click(screen.getByRole("button", { name: "Preview layout" }));
    await user.keyboard("{Control>}k{/Control}");
    // jsdom has no visible header dimensions, so the shortcut uses the record input.
    expect(
      screen.getByRole("textbox", { name: "Search students" }),
    ).toHaveFocus();
    await user.type(
      screen.getByRole("textbox", { name: "Workspace search" }),
      "Kwame",
    );
    expect(screen.getAllByRole("row")).toHaveLength(2);
    expect(
      screen.getByRole("textbox", { name: "Search students" }),
    ).toHaveValue("Kwame");
    await user.click(
      screen.getByRole("button", { name: "View recognition activity" }),
    );
    expect(screen.getByRole("link", { name: "Activity log" })).toHaveAttribute(
      "aria-current",
      "location",
    );
  } finally {
    if (scroll)
      Object.defineProperty(Element.prototype, "scrollIntoView", scroll);
    else Reflect.deleteProperty(Element.prototype, "scrollIntoView");
  }
});

it("selects attendance rows for a filtered export without deleting records", async () => {
  const user = userEvent.setup();
  render(<Dashboard />);
  await screen.findByText("No active session");
  await user.click(screen.getByRole("button", { name: "Preview layout" }));
  await user.click(
    screen.getByRole("checkbox", { name: "Select Kwame Mensah" }),
  );
  expect(screen.getByText("1 selected")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Export selected" })).toBeEnabled();
  await user.click(
    screen.getByRole("checkbox", { name: "Select all visible students" }),
  );
  expect(screen.getByText("4 selected")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Clear" }));
  expect(
    screen.queryByRole("button", { name: "Export selected" }),
  ).not.toBeInTheDocument();
  expect(screen.getAllByRole("row")).toHaveLength(5);
});
