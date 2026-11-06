# Student enrollment frontend

React 19 + Vite + TypeScript + Tailwind CSS 4 + [shadcn/ui](https://ui.shadcn.com) (new-york,
neutral). The details form renders immediately; the camera is requested only on the capture step,
and submission loading is inline on the submit button.

The capture step is a **live guided video**, not a still-photo booth: it prompts look straight →
turn left → turn right and automatically collects 3 frames per pose (9 total) while the preview
stays live. Long index numbers such as `PS/CSC/24/0016` are supported. The PC sync performs the
final face-quality check with the same InsightFace model used for attendance.

## Commands

```bash
npm ci
npm run dev        # http://localhost:5173, API proxied to BACKEND_ORIGIN (default 127.0.0.1:8000)
npm test           # Vitest + Testing Library
npm run typecheck
npm run build      # outputs dist/
npm run preview    # serve the built dist/
```

Node 22.12+ is required. The backend serves the built `dist/` at `/app`; run `npm run build`
before local FastAPI serving. Docker and Netlify build automatically.

## Configuration

Copy `.env.example` to `.env.local` for local builds, or set the same variables in Netlify:

- `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY` — hybrid inbox mode. **Public anon/publishable
  key only**; never a `service_role` or `sb_secret_…` key.
- `VITE_ENROLL_EXAM` — optional exam code attached to submissions.
- `VITE_API_BASE` — direct mode only; leave empty for same-origin/Vite proxy.

`public/config.js` is copied unchanged to `dist/config.js` as an optional runtime override for
older/drag-and-drop deployments. Non-empty `VITE_*` build variables take precedence.

## Deployment

Git-connected Netlify uses the root `netlify.toml` (base `frontend`, build `npm ci && npm run
build`, publish `dist`). For drag & drop, upload **`dist` after building**, not this source folder.
See [../docs/HYBRID_SYNC.md](../docs/HYBRID_SYNC.md) and [../docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md).

shadcn/ui component sources and license are in `src/components/ui/` (`SOURCE.md`, `LICENSE.md`).

## Verified head-pose capture

Phone enrollment now runs MediaPipe Face Landmarker in a module Web Worker on the device.
It does not merely wait three seconds and take a picture. The straight/left/right prompts
require one usable face, a stable measured pose for at least 600ms/three observations, then
three checked frames at least 800ms apart. Incorrect pose, extra faces, missing landmarks,
poor framing, tilt, frozen frames or a hidden tab pause collection/reset the hold. Each JPEG
comes from the exact frame analyzed by the worker, not a later camera frame.

The checker sees unmirrored input; the preview and saved JPEGs are mirrored. Positive yaw
means the person's own left. Initial thresholds: straight within 10 degrees, side turns
18–45 degrees, chin pitch within 20 degrees, head tilt within 18 degrees. These are guidance
thresholds, not clinically calibrated angles. Feedback tells the student to move/turn the
correct way. A pose that cannot be verified within 45 seconds produces a recoverable restart
message. No timed capture bypass is offered when the checker cannot load or the browser is
unsupported. Explicit retry restarts a failed worker.

Use an up-to-date Chrome or Safari supporting module workers, WASM, ImageBitmap,
OffscreenCanvas and WebGL2. Model inference is configured for CPU; MediaPipe still uses
WebGL for image preprocessing. Performance/compatibility needs checking on actual phones.
The worker keeps expensive inference off the React/camera-preview thread. Analysis is serial,
at most about 6 samples/second, with camera snapshots downscaled to at most 640 pixels.

### Hosting/build

`npm run dev` and `npm run build` prepare the runtime files from the locked
`@mediapipe/tasks-vision` package automatically. Netlify's existing `npm ci && npm run build`
command needs no change. The 3.8MB model is included in `public/pose/`; its checksum is
validated before builds. Generated WASM/loaders are ignored by Git and copied to
`public/pose/wasm/`. All runtime assets are same-origin, including when served at `/app/`.
No third-party CDN or cloud inference endpoint is needed, but the first phone visit must
load the model and chosen WASM runtime. This uses phone resources, not Netlify server RAM.
See `public/pose/SOURCES.md` for model provenance/checksum and license notices.

### Limits/security

This is capture guidance, **not a robust anti-spoofing/identity-continuity guarantee**.
A replay with appropriate head turns may pass, and different people could take turns in
front of the camera. Browser-side checks are not a trusted security boundary: someone who
bypasses the page can submit arbitrary pose labels. The existing server/sync checks usable
faces and creates InsightFace embeddings; it does not independently enforce these pose
thresholds. Enrollment payload and Supabase table schema are unchanged. No landmark data,
angles or extra live video is uploaded; only the nine selected enrollment JPEGs are submitted.

Tests cover gating, wrong direction, no/multiple faces, loading failures, stable holds,
missing matrices, mirroring, stale frames and worker cleanup. Actual Chromium/WASM tests
confirmed no-face rejection and that a stationary frontal fixture cannot complete the left
step, at both root hosting and `/app/`. Direction/lighting/latency still need real-phone trials.
