import React from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { DemoControls } from "@/components/demo-controls";
const people = [
  {
    student_no: "PS/CSC/24/0016",
    full_name: "Ama Demo",
    face_samples: 9,
    registered: true,
    ready: true,
    reasons: [],
  },
  {
    student_no: "VOL-2",
    full_name: "Kofi Demo",
    face_samples: 0,
    registered: false,
    ready: false,
    reasons: ["No face samples"],
  },
];
const requests: { path: string; body: unknown }[] = [];
beforeEach(() => {
  requests.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, options?: RequestInit) => {
      const body = options?.body ? JSON.parse(String(options.body)) : undefined;
      if (body) requests.push({ path, body });
      let data: unknown = {};
      if (path.endsWith("control/status"))
        data = {
          running: false,
          kind: null,
          exit_code: null,
          log: [],
          sync_configured: true,
        };
      else if (path.endsWith("exams"))
        data = [
          { id: 1, course_code: "CS101", course_title: "Demo examination" },
        ];
      else if (path.includes("readiness")) data = people;
      else if (path.endsWith("demo/reset/preview"))
        data = {
          token: "reset-token",
          counts: {
            attendance_records: 3,
            activity_events: 5,
            identified_count: 2,
          },
        };
      else if (path.endsWith("delete/preview"))
        data = {
          token: "preview-token",
          students: people.filter((p) =>
            body.student_nos.includes(p.student_no),
          ),
          counts: { embeddings: 9, registrations: 1, attendance: 1 },
          warning: "Local deletion only. Supabase is preserved.",
        };
      else data = { message: "Operation complete" };
      return { ok: true, json: async () => data };
    }),
  );
});
it("shows the roster and sends camera start/stop tasks only on user action", async () => {
  const user = userEvent.setup();
  render(<DemoControls onChanged={() => {}} />);
  await user.click(screen.getByRole("button", { name: "Demo controls" }));
  await screen.findByText("Ama Demo");
  expect(requests).toHaveLength(0);
  await user.click(screen.getByRole("button", { name: "Start recognition" }));
  expect(requests[0]).toEqual({
    path: "/api/control/camera/start",
    body: { camera: 0, demo_mode: true },
  });
});
it("requires preview and typed confirmation before removal", async () => {
  const user = userEvent.setup();
  render(<DemoControls onChanged={() => {}} />);
  await user.click(screen.getByRole("button", { name: "Demo controls" }));
  await screen.findByText("Ama Demo");
  await user.click(screen.getByRole("checkbox", { name: "Select Ama Demo" }));
  await user.click(screen.getByText("Advanced student deletion"));
  await user.click(screen.getByRole("button", { name: "Remove selected…" }));
  expect(
    await screen.findByRole("region", { name: "Confirm local deletion" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Permanently remove" }),
  ).toBeDisabled();
  await user.type(
    screen.getByRole("textbox", { name: "Deletion confirmation" }),
    "DELETE",
  );
  await user.click(screen.getByRole("button", { name: "Permanently remove" }));
  expect(requests.at(-1)).toEqual({
    path: "/api/control/delete/confirm",
    body: { token: "preview-token", confirmation: "DELETE" },
  });
});
it("keep-only previews the complement, not the selected people", async () => {
  const user = userEvent.setup();
  render(<DemoControls onChanged={() => {}} />);
  await user.click(screen.getByRole("button", { name: "Demo controls" }));
  await screen.findByText("Ama Demo");
  await user.click(screen.getByRole("checkbox", { name: "Select Ama Demo" }));
  await user.click(screen.getByText("Advanced student deletion"));
  await user.click(
    screen.getByRole("button", { name: "Delete other students…" }),
  );
  expect(requests.at(-1)).toEqual({
    path: "/api/control/delete/preview",
    body: { student_nos: ["VOL-2"] },
  });
  const preview = await screen.findByRole("region", {
    name: "Confirm local deletion",
  });
  expect(within(preview).getByText(/Kofi Demo/)).toBeInTheDocument();
});
it("disables real controls during fictional layout preview", () => {
  render(<DemoControls disabled onChanged={() => {}} />);
  expect(screen.getByRole("button", { name: "Demo controls" })).toBeDisabled();
});

it("selects a phone without auto-starting and checks the chosen device", async () => {
  const user = userEvent.setup();
  render(<DemoControls onChanged={() => {}} />);
  await user.click(screen.getByRole("button", { name: "Demo controls" }));
  await screen.findByText("Ama Demo");
  await user.click(screen.getByRole("button", { name: "Phone / DroidCam" }));
  expect(requests).toHaveLength(0);
  expect(screen.getByRole("spinbutton", { name: "Camera number" })).toHaveValue(
    1,
  );
  expect(screen.getByText(/starting guess/)).toBeInTheDocument();
  await user.clear(screen.getByRole("spinbutton", { name: "Camera number" }));
  await user.type(
    screen.getByRole("spinbutton", { name: "Camera number" }),
    "2",
  );
  await user.click(screen.getByRole("button", { name: "Check camera" }));
  expect(requests[0]).toEqual({
    path: "/api/control/camera/check",
    body: { camera: 2, source: "droidcam", capture_backend: "auto" },
  });
});

it("offers Windows DroidCam backends and sends the explicitly chosen backend", async () => {
  const originalFetch = fetch;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, options?: RequestInit) => {
      const response = await originalFetch(path, options);
      if (path.endsWith("control/status"))
        return {
          ...response,
          json: async () => ({ ...(await response.json()), platform: "win32" }),
        };
      return response;
    }),
  );
  const user = userEvent.setup();
  render(<DemoControls onChanged={() => {}} />);
  await user.click(screen.getByRole("button", { name: "Demo controls" }));
  await screen.findByText("Ama Demo");
  await user.click(screen.getByRole("button", { name: "Phone / DroidCam" }));
  expect(screen.getByRole("combobox", { name: "Capture backend" })).toHaveValue(
    "dshow",
  );
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Capture backend" }),
    "msmf",
  );
  await user.click(screen.getByRole("button", { name: "Check camera" }));
  expect(requests.at(-1)).toEqual({
    path: "/api/control/camera/check",
    body: { camera: 1, source: "droidcam", capture_backend: "msmf" },
  });
});

it("keeps Windows options selectable if an older backend omits its platform", async () => {
  const user = userEvent.setup();
  render(<DemoControls onChanged={() => {}} />);
  await user.click(screen.getByRole("button", { name: "Demo controls" }));
  await screen.findByText("Ama Demo");
  expect(screen.getByText(/Backend platform:/)).toHaveTextContent(
    "not reported",
  );
  const select = screen.getByRole("combobox", { name: "Capture backend" });
  await user.selectOptions(select, "dshow");
  expect(select).toHaveValue("dshow");
  await user.selectOptions(select, "msmf");
  expect(select).toHaveValue("msmf");
  expect(screen.getByRole("option", { name: /DirectShow/ })).not.toBeDisabled();
});

it("needs no examination selector or manual registration", async () => {
  const user = userEvent.setup();
  render(<DemoControls onChanged={() => {}} />);
  await user.click(screen.getByRole("button", { name: "Demo controls" }));
  await screen.findByText("Ama Demo");
  expect(screen.queryByText("Test classroom 1")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /Register/ }),
  ).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Examination")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Start recognition" }));
  expect(requests.at(-1)?.body).toEqual({ camera: 0, demo_mode: true });
});

it("previews counts, keeps review visible, and confirms a combined reset", async () => {
  const user = userEvent.setup();
  const changed = vi.fn();
  render(<DemoControls onChanged={changed} />);
  await user.click(screen.getByRole("button", { name: "Demo controls" }));
  await screen.findByText("Ama Demo");
  await user.click(screen.getByRole("button", { name: "Reset demonstration" }));
  const review = await screen.findByRole("region", {
    name: "Confirm demonstration reset",
  });
  expect(within(review).getByText("attendance records: 3")).toBeInTheDocument();
  expect(within(review).getByText("activity events: 5")).toBeInTheDocument();
  expect(requests).toEqual([
    { path: "/api/control/demo/reset/preview", body: {} },
  ]);
  await user.click(
    within(review).getByRole("button", { name: "Confirm reset demonstration" }),
  );
  expect(requests.at(-1)).toEqual({
    path: "/api/control/demo/reset/confirm",
    body: { token: "reset-token", confirmation: "RESET" },
  });
  expect(changed).toHaveBeenCalledOnce();
});

it("canceling reset never clears records", async () => {
  const user = userEvent.setup();
  render(<DemoControls onChanged={() => {}} />);
  await user.click(screen.getByRole("button", { name: "Demo controls" }));
  await screen.findByText("Ama Demo");
  await user.click(screen.getByRole("button", { name: "Reset demonstration" }));
  const review = await screen.findByRole("region", {
    name: "Confirm demonstration reset",
  });
  await user.click(within(review).getByRole("button", { name: "Cancel" }));
  expect(requests).toHaveLength(1);
  expect(
    screen.queryByRole("region", { name: "Confirm demonstration reset" }),
  ).not.toBeInTheDocument();
});

it("uses the selected DroidCam device for local enrollment without cloud calls", async () => {
  const user = userEvent.setup();
  render(<DemoControls onChanged={() => {}} />);
  await user.click(screen.getByRole("button", { name: "Demo controls" }));
  await screen.findByText("Ama Demo");
  await user.click(screen.getByRole("button", { name: "Phone / DroidCam" }));
  await user.type(
    screen.getByRole("textbox", { name: "Local volunteer ID" }),
    "VOL-NEW",
  );
  await user.type(
    screen.getByRole("textbox", { name: "Local volunteer full name" }),
    "New Volunteer",
  );
  await user.click(
    screen.getByRole("button", { name: "Start local enrollment" }),
  );
  expect(requests).toEqual([
    {
      path: "/api/control/demo/enroll",
      body: {
        camera: 1,
        source: "droidcam",
        capture_backend: "auto",
        student_no: "VOL-NEW",
        full_name: "New Volunteer",
        replace_existing: false,
      },
    },
  ]);
});

it("stops active recognition before previewing reset", async () => {
  const originalFetch = globalThis.fetch;
  let stopped = false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, options?: RequestInit) => {
      if (path.endsWith("control/status"))
        return {
          ok: true,
          json: async () => ({
            running: !stopped,
            kind: "camera",
            log: [],
            sync_configured: true,
          }),
        };
      if (path.endsWith("camera/stop")) stopped = true;
      return originalFetch(path, options);
    }),
  );
  const user = userEvent.setup();
  render(<DemoControls onChanged={() => {}} />);
  await user.click(screen.getByRole("button", { name: "Demo controls" }));
  await screen.findByText("Ama Demo");
  expect(
    screen.getByRole("button", { name: "Start local enrollment" }),
  ).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Reset demonstration" }));
  await screen.findByRole("region", { name: "Confirm demonstration reset" });
  expect(requests.map((r) => r.path)).toEqual([
    "/api/control/camera/stop",
    "/api/control/demo/reset/preview",
  ]);
});

it("shows a failed reset preview without offering confirmation", async () => {
  const originalFetch = globalThis.fetch;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, options?: RequestInit) => {
      if (path.endsWith("demo/reset/preview"))
        return {
          ok: false,
          json: async () => ({ detail: "Close external camera first" }),
        };
      return originalFetch(path, options);
    }),
  );
  const user = userEvent.setup();
  render(<DemoControls onChanged={() => {}} />);
  await user.click(screen.getByRole("button", { name: "Demo controls" }));
  await screen.findByText("Ama Demo");
  await user.click(screen.getByRole("button", { name: "Reset demonstration" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Close external camera first",
  );
  expect(
    screen.queryByRole("region", { name: "Confirm demonstration reset" }),
  ).not.toBeInTheDocument();
});
