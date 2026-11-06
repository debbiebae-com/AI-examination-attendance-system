# Clickable ExamLens launcher (Windows)

For the Electron desktop window, use **Prepare Desktop App.cmd** then **ExamLens Desktop**
(or **Start Desktop App.cmd**). See [desktop instructions](../desktop/README.md). The browser
launcher below remains a backup; desktop startup reuses the same ownership/readiness checks.

This is a local presentation launcher, not an installer or a hosted deployment. It keeps
this checkout, its working camera setup and its existing local student database. No camera
connection, source setting, student record or attendance is changed by preparation/startup.
It uses Windows PowerShell 5.1, Node.js 22.12+ and uv already installed on the PC. Run as your
normal Windows user, not as administrator.

## First time (and after pulling an app update)

1. Stop recognition and close any **old manually started** backend/npm terminal windows.
   If you used this launcher before, use **Stop Demo.cmd** instead.
2. Keep internet available, and double-click **Prepare Demo.cmd** in the repository root.
   It can take a while. It synchronizes the locked backend vision dependencies, loads the
   full enrollment/recognition model pack (downloading missing files), runs `npm ci` with
   build dependencies, and creates a production Next.js build. It does not open a camera
   or access student/attendance data. The setup window stays open so failures are visible.
3. Wait for the green **Ready** message. An **ExamLens** desktop shortcut is created if that
   name is unused and the Desktop is writable. Otherwise, use **Start Demo.cmd** directly.
4. Double-click **Start Demo.cmd**. It briefly displays startup progress, starts hidden
   background servers, checks their HTTP readiness, and opens `http://127.0.0.1:3000` in your
   default browser. No server commands need to be typed.

Do not copy just the shortcut/CMD files to another folder: they refer to the checkout and
its installed environment/build. Moving the checkout requires preparing it again and
recreating the desktop shortcut if its target changed. Preparation is per-PC; it is not a
portable executable or an installation of Node/Python/uv themselves.

## Presentation day

1. Connect DroidCam manually exactly as you do now (or use the laptop webcam).
2. Double-click **ExamLens** on the Desktop or **Start Demo.cmd** in the project folder.
3. Use the dashboard for recognition, local enrollment, sync and resetting demonstrations.
4. When finished, double-click **Stop Demo.cmd** in the project folder. It requests a safe
   stop for dashboard-started recognition/enrollment, waits for work to finish, then stops
   only the launcher's own API/dashboard process trees. Face data and attendance are kept.

Closing the browser does **not** close the servers. Double-clicking Start again opens the
existing healthy owned dashboard rather than launching duplicates. Simultaneous clicks
are serialized; a second click during startup is told to wait. If an old launch is only
partially alive, use Stop then Start.

## Offline rehearsal

Prepare once while online, successfully try recognition **and local guided enrollment**,
then stop ExamLens, disconnect internet, and double-click Start again. The ordinary launcher
uses the existing environment with `uv run --offline --no-sync` and the existing production
build: it does not run dependency installation, development compilation or model warmup.
Keep the prepared environment, `dashboard/node_modules`, `dashboard/.next` and your cached
InsightFace models on this PC. Removing/changing them can require preparation again.
Online enrollment-link submissions/cloud sync still need internet; **Enroll locally** does
not. DroidCam still needs its local USB/Wi-Fi connection and working PC client. External
General Sans font loading may fail offline; the bundled font fallback remains available.

## Startup safeguards and troubleshooting

- App/build fingerprints detect a changed source tree, lockfile or build ID and request
  **Prepare Demo.cmd** again rather than serving an outdated production UI.
- Ports 8000 and 3000 must be available, or already owned by this launcher's verified server
  trees. Foreign/manual servers are not adopted or killed. Close their original windows
  once. A healthy reused launch is verified using PID **and creation time**, listener
  ownership and HTTP responses; reused PID numbers alone are not trusted.
- Startup waits for API `/health`, dashboard HTML and its `/api/live/session` proxy. Each
  service has a two-minute readiness deadline. Failed starts clean up only processes
  created by that attempt. The launcher forces its dashboard's process-local backend URL
  and control-key path to this checkout, not a previous hosted API setting.
- The backend loads `backend/.env` if present, without displaying it. Browser-facing calls
  still go through the dashboard's same-origin proxy. The launcher binds both servers to
  loopback only; it does not expose a new phone enrollment server to the network.
- If a camera task is taking a long time to load/finish, Stop waits up to two minutes and
  otherwise leaves the servers open. Wait for the task, or close/cancel its camera window,
  then click Stop again. An externally started/unclosed recognition session must be closed
  first; the launcher will not force-kill unrelated/external processes.
- Private logs/state are under **`.demo-runtime`** in this checkout. Server stdout and stderr
  are in separate timestamped files. If startup fails, the launch window stays open and
  points to this folder. Logs may contain student identities/errors; keep them private.
  Never share `.env`, `control.key`, model data or enrollment images. Runtime files are
  ignored by Git. Do not delete `servers.json` while managed servers are running; Stop uses
  it to identify what it owns.
- If Windows reports missing uv/Node, install those prerequisites using the existing
  project setup instructions, then retry Prepare. This script does not change machine-wide
  execution policy or require admin permissions. Organization-enforced PowerShell policy
  may still prohibit scripts.

The launcher has grammar/static regression checks in this Linux development environment;
**Windows process creation, shortcuts and shutdown must still be smoke-tested on the actual
presentation PC**. No sandbox result claims a physical Windows/DroidCam run.
