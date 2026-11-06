# ExamLens desktop app (Windows presentation PC)

An Electron application window around the existing production dashboard. This increment
uses this checkout's prepared Python environment, Node runtime and cached InsightFace models;
it is **not** a standalone installer or a portable executable. The ordinary browser launcher
remains a backup. No camera drivers, source settings or recognition algorithms are changed.

## Set up once, online

1. Stop recognition and existing servers. Use **Stop Demo.cmd** for managed servers, or close
   old manually started terminal windows.
2. Double-click **Prepare Desktop App.cmd** in the repository root. This includes backend
   dependencies/model warmup, the production dashboard build, and the pinned Electron runtime
   download. Wait for **Ready**. No camera is opened and student data is not modified.
3. Open the new **ExamLens Desktop** desktop shortcut. It points directly to Electron with
   this app folder as its argument. If shortcut creation is unavailable, double-click
   **Start Desktop App.cmd** in the project folder instead. Do not use the old **ExamLens**
   browser shortcut when you want the desktop window.

## Use

- A branded loading screen remains while the launcher starts/checks the local API, dashboard
  and proxy. The dashboard then opens **inside ExamLens**, not in a browser tab.
- Connect DroidCam manually as usual. Recognition and guided enrollment still open their
  existing native OpenCV windows on this PC; Electron does not capture browser video.
- A second launch focuses the existing app. It does not start another set of services.
- Closing the main window or choosing **ExamLens → Exit** requests a cooperative task stop,
  then closes the servers owned by this desktop launch. While waiting, the window shows a
  closing message. If work cannot stop safely, the window remains open and explains that
  you should finish/cancel the active task, then close it again. Enrollment data and saved
  attendance are not deleted by exiting.
- If Start Demo/browser-owned services were already running, the app may reuse them but
  leaves those independently owned services running on exit. Use Stop Demo for those. A
  desktop launch can reclaim its own previous desktop service state after an app crash.
- CSV export uses Electron's normal Save dialog. Remote navigation, pop-up windows, renderer
  Node access and renderer camera permissions are disabled. Local native camera tasks use
  the already selected working camera path, including DroidCam.

Preparation must be rerun after app changes. After preparing, rehearse start/recognize/local
enrollment/reset/exit with internet disconnected. Desktop startup does not install packages
or download models. Online sync still needs internet. Keep the checkout, `.venv`, dashboard
build/dependencies and `desktop/node_modules` in place; the desktop shortcut is not a copy
of the application. This version still requires installed system Node and uv.

## Failures and privacy

Startup errors appear as native dialogs. **ExamLens → Open private log folder** opens
`.demo-runtime`. `desktop.log` contains launcher output; timestamped service logs are there
as well. Keep logs private: they may contain names/errors. No environment file or control key
is passed into the renderer. Startup/shutdown uses the existing local ownership-checked
PowerShell launcher with an app-specific UUID; a desktop close does not kill arbitrary
Python/Node processes. Stop Demo remains the manual clickable recovery path.

## Development checks

`npm ci` in this folder downloads the Electron binary for the current platform. `npm test`
runs dependency-free Node lifecycle/security regression tests; it does not launch Electron.
The Linux sandbox validated these tests, dependency audit, JavaScript syntax and PowerShell
grammar, but **cannot validate Win32 native windows, shortcuts, shutdown or physical DroidCam**.
Smoke-test Prepare Desktop → open → recognize → reset → exit → reopen on the presentation PC,
including closing during startup and closing while guided capture is active.
