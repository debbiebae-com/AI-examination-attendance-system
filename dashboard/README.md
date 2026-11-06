# ExamLens — local recognition dashboard

Next.js App Router, TypeScript, Tailwind CSS and shadcn/ui (Radix primitives).
This is a separate application: `frontend/` remains the Netlify phone-enrollment site.
Do not point the existing enrollment Netlify build at this directory.

## Start on your PC

Use Node **22.12+**. First get this branch's latest files onto your PC. Open three
PowerShell windows, each initially at the repository root.

**Window 1 — API:**

```powershell
cd backend
uv sync --frozen --extra vision
uv run --frozen --extra vision uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Window 2 — recognition:**

```powershell
cd backend
uv run --frozen --extra vision python -m app.vision.attend --exam CS101 --det-size 480 --threads 4
```

Use an exam that exists and already-enrolled volunteers. Do not reset or reseed your
volunteer database. Both backend processes must use the same checkout/data folder.

**Window 3 — dashboard:**

```powershell
cd dashboard
npm ci
npm run dev -- --hostname 127.0.0.1
```

Open **http://localhost:3000** on that PC. Press `q` in the camera window to stop
recognition; the dashboard will show a stopped session, not pretend the camera is active.
After installation and the model download, normal local operation needs no internet.
Geist fonts are bundled through npm, not fetched from Google at runtime.

Production build (optional): `npm run build`, then `npm run start -- --hostname 127.0.0.1`.
The development/preview default binds 0.0.0.0 to support Arena live previews; the commands
above override this for a PC-only demo. This dashboard/API has no user-login system and
must **not** be deployed as a public organizer interface.

## Data connection

Browser requests use relative `/api/*` URLs. Next's server proxies only allowlisted,
read paths and explicit demo-control POST paths to `BACKEND_ORIGIN` (defaults to `http://127.0.0.1:8000`). This is a
server-only setting; never set a browser-facing URL to localhost for a different PC.
For a nondefault local backend port, set `$env:BACKEND_ORIGIN` before starting Next.

Every two seconds the dashboard refreshes the snapshot, student metadata and selected
exam's attendance. Requests are serialized with timeouts; stopping/unmounting aborts
outstanding requests. Session-ID changes clear the selected student. Network errors show
an alert, hide numeric metrics and disable exports; retained table rows are explicitly stale.

- **Identified students:** distinct identities confirmed in this session.
- **Unidentified now:** currently visible unknown tracks after the backend grace period;
  not a count of unique unknown people.
- **Marked present:** saved attendance for the selected exam, including earlier runs.
- Recognition success is not silently equated with a successful attendance write.
- Recent activity uses the backend's bounded 100-event snapshot (30 displayed at once).
- GMT times interpret the database's timezone-naive timestamps as UTC.

Student details use locally supplied enrollment fields plus the explicitly agreed
presentation index rules below. They are not verified university records. Other
departments remain not supplied.
Portraits are not exposed by the current API, so initials are shown with an explicit
placeholder notice. Camera video remains in the OpenCV window; the dashboard does not
open a second camera. Consent-based portraits remain follow-up work.

## Layout preview

**Preview layout** opts into fictional sample data, with a prominent illustration banner.
It does not enroll anyone, mark attendance, or write to the database. Preview CSV filenames
start with `ILLUSTRATION-`. **Connect live data** or **Exit preview** reconnects the real API.
The default is always live mode with truthful loading, idle or disconnected states.

## Checks

```powershell
npm test
npm run build
npm audit
```

Tests cover idle/disconnected state, illustration opt-in/exit, student search/detail dialog,
live attendance distinctions, long indices, UTC formatting and CSV escaping. The local API
proxy can be checked at `http://localhost:3000/api/live/session`. No real-camera performance
claims are made by these UI tests. Real multi-person trials remain necessary.

## Demo controls — no repeated terminal commands

After downloading this version, stop old API/Next/camera windows once. On Windows,
double-click **Start Demo.cmd** in the repository root. It opens the backend and dashboard
servers in two windows; leave them open. Visit http://localhost:3000, then **Demo controls**.
Node 22.12+, uv and initial model/package downloads are still prerequisites. The launcher
installs locked dashboard dependencies and starts the backend with its vision extra.
It is a Windows convenience launcher, not an installed service; do not launch duplicates.

From the dashboard you can:
- Select an existing exam and camera number; start recognition at detector size 480/four threads.
- Stop a dashboard-started camera cooperatively (after inference/model loading finishes).
- Sync pending phone submissions; see bounded progress/output and task exit status.
- View **all local volunteers**, face-sample counts, registration and readiness reasons.
- Register selected volunteers for the chosen exam, without altering fee/suspension flags.
- Remove selected volunteers, or **keep only selected** and preview removal of everyone else.

Deletion requires a server-generated preview and typing DELETE. Preview tokens expire after
two minutes, are single-use, and records are checked again before deletion. Students, face
embeddings, registrations and their attendance are removed; **exams stay**. No operation
runs merely because you opened the panel. Real controls are disabled in layout preview.
Camera/gallery operations are mutually exclusive; an external camera must be stopped with q.
An unresponsive/stale external camera is blocked conservatively, not force-killed.

**Local deletion is not cloud deletion.** Supabase inbox submissions are preserved and a
pending submission can recreate a student at the next sync. Cloud inbox purge, editing student
academic data, and exam creation are not exposed in this first control panel.

### One-time private sync configuration

Copy `backend/.env.example` to `backend/.env` and set the real project URL and service-role
key **in that local file only**. The launcher passes it to uv's env-file option, and sync
children inherit the settings. Keep the file private; never put this key in Netlify or the
browser. If your API is started manually, use:

```powershell
cd backend
uv run --frozen --extra vision --env-file .env uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Without the private config, camera/roster controls still work; sync stays disabled. Restart
the backend after changing environment settings. ENROLL_MODEL sets the model for both
managed sync and managed recognition; it must match existing gallery embeddings.

### Local control protection and limits

The backend generates `backend/data/control.key` with owner-only POSIX creation permissions.
Next reads it server-side and sends it to the API; it is **never sent to browser JavaScript**.
Keep the checkout and this key private on Windows too. POST controls also reject cross-origin
requests. Override LOCAL_CONTROL_KEY_FILE only on the Next server if your layout differs.
Keep both servers bound to loopback and use **one backend worker**. This is not a public
multiuser administration service. Anyone allowed to access this local Next server can use
its controls; the secret is an internal server-to-server guard, not a user login.

The backend must remain running while a managed task runs. Close the camera using Stop
before shutting down the API; an unexpected API crash can orphan a child process. Close
that camera with q before restarting. Sync is not forcibly cancelled mid-import; failures
and partial sync details appear in its output. Async job metadata is in memory, not a job
queue persisted across API restarts. Do not use `uvicorn --reload` during the demonstration.

## Presentation academic details

For this demonstration, the backend display mapper recognizes indices in the form
`PS/CSC/24/0016` (case-insensitive):
- Programme code **CSC** displays department **Computer Science and Information Technology**.
- Index year code **24** displays **Level 300**, independent of the recorded level.
- Other year codes are not extrapolated. They retain the locally stored level.
- Unrecognized department codes remain not supplied. Programme text remains locally stored.

The API retains original `programme`/`level` and adds a separate `presentation` object.
The student list, latest-recognition/saved-record card and details panel use those display
fields. The details panel explains the assumptions; these are not verified university data
and never change recognition, registration or eligibility. The dashboard also enforces these
two display rules in `lib/data.ts`: CSC and year code 24 take priority even when an older API
omits `presentation` or returns a stale display level. Other index years retain supplied values;
no automatic year progression is inferred. Layout-preview fixtures are fictional.

The OpenCV scan window uses the same backend mapper: confirmed identities show name/status,
index, level, department and a presentation-metadata notice. Unknown/checking faces do not get
academic identity details. The top banner shows the exam/venue, with processed FPS separate.
Cards wrap long lines to fit the frame. Crowded/occluded face cards can still overlap; real
multi-person camera testing is necessary before the presentation.

## shadcn Neutral redesign

The dashboard uses the configured shadcn **New York / Neutral** theme and CSS variables,
without a green primary override. Geist is bundled locally. Shared shadcn-style Card,
Button, Input, Badge, Table and Radix Tabs primitives provide the workspace layout:
compact sidebar, examination summary, measured counts, searchable student records,
latest-student panel, activity log and neutral detail/control panels. Green is reserved
for successful/active statuses; amber/red indicate attention/errors. No fabricated trends,
percentages or decorative charts are added. The mobile sidebar is toggleable; record
tables scroll horizontally without widening the page. Filters support keyboard navigation.
Camera/sync/registration/removal controls keep their existing behavior and safeguards.

Regression tests specifically assert `PS/CSC/24/0016` -> **Level 300** in both the table
and profile against an older API with stored level 100 and no display metadata, plus
stale display overrides, unspecified year-code fallback and non-mutating behavior.

## Current design iteration — Radix Themes + supplied teal palette

This supersedes the stock Neutral colour treatment above. Following Radix's
[getting started](https://www.radix-ui.com/themes/docs/overview/getting-started),
[styling](https://www.radix-ui.com/themes/docs/overview/styling) and
[colour](https://www.radix-ui.com/themes/docs/theme/color) guidance, iteration 1 installs
`@radix-ui/themes`, wraps the root in its light Theme, and starts migration with native
Heading/Text and statistic Cards. Radix CSS has its own cascade layer before utilities.
The remaining shadcn components/controls intentionally remain in place for this review.

The supplied palette is #04222B, #0A3D4A, #10606F, #1D8B94, #4FB8B4, #98D8D0 and
#E2F4F0. CSS variables map it to both libraries, with lighter companion steps for the
Radix 12-step accent scale. Dark ink and deeper teal are used for readable text/actions;
light mint and brighter teals are surfaces/accents, not white-on-light-teal body text.

**Review gate:** inspect palette, typography and surface treatment before changing layout.
No charts or chart dependencies have been added yet. Proposed next iteration, only after
approval: one Recharts/shadcn-style attendance-over-time chart derived from the selected
exam's saved attendance timestamps, with honest empty/offline/illustration states. Do not
infer absent students from the full local gallery or treat unknown tracks as unique people.

### Iteration 2 — saturated palette and Recharts

The workspace now uses a saturated #10606F canvas, dark teal navigation/header and filled
statistic cards. Pale/white surfaces are retained for dense tables, chart axes and control
panels for readability, not as the dominant workspace colour.

Two responsive Recharts visuals use the selected exam's saved attendance only:
- Cumulative attendance: chronological UTC/GMT minute buckets, stepped line and area.
  Points start at the first saved bucket; no invented baseline or missing students.
- Attendance by level: unique saved students grouped by presentation level (24 -> 300).
  Missing metadata is explicitly "Not supplied". This is not the entire enrolled gallery.

Duplicate student records count once (earliest valid timestamp); malformed timestamps are
omitted from the timeline with a notice but still counted in the level chart. Empty, loading
and disconnected charts show text instead of fabricated series. Chart animations are off;
time-series values are also available as text. Layout preview uses explicitly fictional,
spaced-out timestamps so the time chart can be inspected. No real attendance is modified.
