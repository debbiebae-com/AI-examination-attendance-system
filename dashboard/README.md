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
above override this for a PC-only demo. This dashboard/API has no new authentication and
must **not** be deployed as a public organizer interface.

## Data connection

Browser requests use relative `/api/*` URLs. Next's server proxies only allowlisted,
read-only paths to `BACKEND_ORIGIN` (defaults to `http://127.0.0.1:8000`). This is a
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

Student details use actual locally supplied enrollment fields. They are not verified
university records. Department is shown as not supplied; no department is invented.
Portraits are not exposed by the current API, so initials are shown with an explicit
placeholder notice. Camera video remains in the OpenCV window; the dashboard does not
open a second camera. Consent-based portraits and richer demo metadata remain follow-up work.

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
