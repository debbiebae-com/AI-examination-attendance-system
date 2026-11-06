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

**Preferred desktop window:** run **Prepare Desktop App.cmd** once, then open the
**ExamLens Desktop** shortcut or **Start Desktop App.cmd**. It displays this dashboard inside
Electron and manages its servers. See [desktop instructions](../desktop/README.md).
The browser-launcher instructions below remain available as a backup.

Windows startup is now clickable. Stop old manually started servers once, then:

1. Double-click **Prepare Demo.cmd** while online. It installs locked dependencies, warms
   the full face model pack without opening a camera, and builds the production dashboard.
2. On presentation day, double-click **Start Demo.cmd** (or the **ExamLens** desktop shortcut
   created during preparation). It starts background servers and opens the browser after
   the backend, dashboard and API proxy are healthy. No dependency installs or development
   builds run on an ordinary launch. A second click reopens the existing owned dashboard.
3. Use **Stop Demo.cmd** when finished. Closing the browser alone does not stop servers.

See [the Windows launcher guide](../docs/PRESENTATION_LAUNCHER.md) for offline rehearsal,
updates, logs and port conflicts. Node 22.12+, uv and first-time internet access are required.
Rerun Prepare after an app update. Camera/DroidCam connection is manual and unchanged.

From the dashboard you can select the working camera, start/stop recognition, reset a
recognition demonstration, sync online submissions, enroll locally through PC/DroidCam,
and inspect all local volunteers' face-sample readiness. No manual exam registration is
needed in demonstration mode. Advanced student deletion remains separate.

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

### Current iteration — dark enterprise / amber

Supersedes the teal palette: #1A1A1A canvas, #222222 surfaces, #2A2A2A borders,
#E8822A actions/chart bars, no decorative shadows. Sidebar is 224px; the 56px header
is sticky, with shared quick search, Ctrl/Cmd+K focus, real activity-log navigation and
fullscreen toggle. There is no notification backend or invented unread count. The footer
profile is explicitly a local operator, not an authenticated account or subscription plan.
Labels are lighter than the suggested #666666 to retain readable dark-mode contrast.

General Sans uses Fontshare's hosted stylesheet/API (online). The existing locally bundled
Geist font is the offline fallback. No third-party General Sans font binary is republished
in this public repository. Only font loading requires that external service; local demo
operations and fallback typography continue without internet.

Metric mini bars show up to five actual poll snapshots, reset for a new session/mode;
initially there may be only one bar. No fabricated historical bars or growth percentages.
The grouped attendance chart compares cumulative saved records with new records in each
recorded minute, highlighting the latest recorded bucket (not a fictitious current month).
All bars use the same amber, varying opacity. The secondary summary is deterministic
record aggregation, not an AI-generated insight. The table stays examination-specific,
without fabricated transactions, prices, sales, or subscription metadata.

The records table is full-width with row selection, select-all-visible, clear selection and
selected-only attendance CSV export. Selected exports include saved attendance only and use
`-selected` filenames; selection is not a destructive action. New session/mode clears it.
Browser checks cover this filtered CSV and shortcut focus in addition to existing controls.
Fontshare cannot be reached in the sandbox browser, so its screenshots use the bundled
fallback; General Sans loading must be checked on an internet-connected presentation PC.

## Phone recognition camera — DroidCam virtual webcam

Install and connect the compatible DroidCam phone app **and Windows client/virtual webcam
driver**. An OBS-only source is not enough for OpenCV's webcam selection. The phone feeds
the Windows webcam device; recognition remains on the PC. No phone IP/network URL is
accepted by these endpoints and the dashboard does not install/manage DroidCam itself.

1. Stop existing recognition. Connect the phone in the DroidCam Windows client (USB preferred;
   Wi-Fi works if the client can connect). Confirm video there and keep that connection running.
2. Close competing apps using the virtual webcam (Windows Camera, Teams, Zoom, etc.).
3. Open **Demo controls → Camera for recognition and enrollment → Phone / DroidCam**.
4. Choose a camera number. `1` is a starting guess, **not automatic device discovery**.
   Windows backend choice defaults to DirectShow for this profile; try Automatic or Media
   Foundation if necessary. Device indices can differ by backend and after reconnecting.
5. **Check camera** reads a frame and displays a four-second snapshot in a local PC window.
   Check that the image actually comes from the phone. No identity inference, enrollment or
   attendance writes occur. A slow driver check is terminated after 20 seconds. A successful
   frame check does not prove correct identity, smooth live performance or long-term stability.
6. After the check finishes, click **Start recognition**. Stop before switching
   sources. Last selected camera is shown in task details; running source/index/backend are
   also attached to the live session. The source name is a user selection, not driver identification.

Phone profile retains the format configured by the DroidCam client; it does not force
resolution or frame rate. Some virtual camera drivers return green/corrupt frames when
OpenCV renegotiates these properties. Configure resolution in DroidCam instead; the check
reports actual frame dimensions. Existing PC/default auto capture is unchanged.
Managed recognition retains the existing model choice, ByteTrack, detector size 480 and four
threads. Test this exact phone/cable/backend before presentation day. Actual DroidCam hardware
has not been validated in this sandbox; tests mock camera/device APIs and subprocess launching.
The camera-check child is the only process opened for testing and blocks other demo jobs until
it exits. Gallery/sync/delete operations retain the existing mutual-exclusion guards.

### Green image with FPS overlay

FPS only confirms the recognition loop is processing frames; it does not prove correct
camera content. Stop recognition, confirm the live phone feed in the DroidCam Windows
client, and keep the client connected. In Demo controls, use Check camera with the same
index/backend before starting recognition. Test Automatic, DirectShow and Media Foundation
one at a time; camera numbers can differ by backend. A readable green frame can still pass
the frame-read check, so visual confirmation is essential. Try other indices if necessary.
Current phone capture leaves resolution/FPS negotiation to DroidCam rather than forcing
720p/30. Physical Windows/DroidCam verification remains required.

### Diagnose separately from the dashboard

The backend selector now disables Windows options only for an explicitly non-Windows API
host, not a missing `platform` field. Missing platform is shown as an old/restart-needed
API warning; an older API may ignore new fields, so restart it before a camera test.
Running tasks still lock source settings intentionally. The API enforces platform support.

For evidence rather than trial-and-error, stop recognition/checks, keep DroidCam connected,
and run from a separate PowerShell window at the repository root:

```powershell
git pull --ff-only origin arena/6093045b-ai-examination-attendance-syst
cd backend
uv run --frozen --extra vision python -m app.vision.camera_diagnostics --indices 0 1 2 --preview 2>&1 | Tee-Object -FilePath camera-diagnostics.txt
```

On Windows this compares Automatic, DirectShow and Media Foundation for each index, each
in a fresh subprocess with a 20-second limit. It does not load face models, access the DB,
record attendance, change resolution/FPS or save images. The brief previews need visual
confirmation. Output includes Python bitness/path, installed OpenCV distributions, actual
capture backend, FOURCC, reported conversion/resolution/FPS, frame shape/dtype, read count,
BGR means/std, green dominance, first/last differences and driver errors/timeouts.
Multiple OpenCV distributions are reported as evidence, not automatically removed.

A green scene or stationary phone may produce green dominance/low movement naturally;
these are clues, not an automatic failure verdict. `frames_received` is not device identity.
A targeted follow-up can use `--indices 2 --backends dshow --convert-rgb on` only after
reviewing the baseline. This changes only the diagnostic probe, not recognition settings.
Do not run diagnostics concurrently with recognition or other apps consuming the virtual
webcam. Share the resulting text and identify which preview was correct/green, not photos,
.env files, control keys or service credentials. Windows driver testing is still user-side.

## Recognition demonstration — repeatable rounds and offline enrollment

The current Demo controls flow has **no classroom selector or registration buttons**:

1. Select the working PC webcam or Phone / DroidCam source, index and backend.
2. **Start recognition** to show existing enrolled faces, one or several people at a time.
3. **Reset demonstration** safely requests camera stop and waits for the dashboard-started recognition process to exit (up to three minutes, including model loading). It then previews saved demonstration attendance, activity events and identified count. **Confirm reset demonstration** clears those records/counters together. Cancelling the preview keeps saved data; recognition remains stopped.
4. Click **Start recognition** for a fresh round with the same enrolled faces.

Demonstration mode stores attendance in an automatically created internal `EXAMLENS-DEMO`
record, not CS101 or another real examination. There is no scheduling/classroom management
step. It records enrolled, confirmed matches without checking exam registration, fee clearance
or suspension; it does **not** change those student flags. Ordinary CLI/API exam attendance
retains its eligibility checks. Demo CSV rows have source `demo` and the isolated demo code;
fictional per-person **Demo exam:** overlay labels remain display-only and stable per index.
ByteTrack, buffalo_l/model configuration, recognition thresholds, and driver camera format
are unchanged.

The reset requires authorized local controls and a two-minute, single-use preview. It refuses
changed records, active/external live sessions and concurrent capture/sync/check tasks. It
keeps all student records, face samples, registrations and other exams' saved attendance.
Historic CS101 attendance from older versions is not silently deleted or migrated. The live
view switches to the isolated demonstration scope after starting recognition or resetting.
Export a demonstration round before resetting if you need its results.

### New volunteers: online or local

- **Online:** keep the existing enrollment link, then stop recognition and click **Sync
  submissions**. Start recognition again to reload the gallery. No manual registration step
  is needed for demonstration mode, regardless of the submission's exam assignment.
- **Offline/local:** stop recognition. Enter a volunteer ID/index and name in **Enroll
  locally**, then **Start local enrollment**. The existing guided desktop capture opens on
  the backend PC, using the exact selected source/index/backend above — laptop webcam or
  DroidCam. One person looks straight, turns left, then right. Accepted embeddings are saved
  directly into the local gallery, without Supabase, a phone-browser link or cloud sync.
  Wait for `Saved ... face samples` in task output, then start recognition. The guide does not
  provide certified anti-spoofing; it is the existing guided turn capture, not a new security
  claim.

The PC must already have its vision dependencies and full enrollment model pack installed.
Run a local enrollment once before the event, then test with internet disabled. Models may
need downloading on first use. DroidCam still needs its working PC client and USB/local
Wi-Fi connection; it does not require cloud internet for this local capture path. This is
not an offline multi-phone web-enrollment server.

Use **Cancel enrollment** or q/Esc in the desktop capture window to abandon capture. Stop is
cooperative and may wait for model/inference work. A failed/cancelled capture does not create
an empty student or replace existing samples. Re-enrolling an existing ID requires an
explicit checkbox; successful capture replaces only that person's `capture:` samples,
keeping their stored name, flags, phone samples, registrations and attendance.

**Advanced student deletion** remains separate: **Delete other students…** previews the
unselected people and requires typed `DELETE`. It deletes student data, not just attendance.
Readiness/diagnostic-report expansion is deferred; the roster already shows which people
have face samples. Actual Windows/DroidCam guided capture still requires user-side testing;
sandbox tests simulate devices/models, alongside browser checks of controls and reset flow.
