# Reduced-scope implementation audit

Reviewed 2026-11-06. This is an implementation plan, not a claim of measured recognition performance.

## Implementation progress after the initial audit

ByteTrack is the agreed tracker. The initial audit found the intended integration absent;
that gap is now addressed with Supervision ByteTrack in the attendance loop. SCRFD confidence
scores feed its high/low-confidence association. Identity confirmation is reset when observations
contradict a confirmed identity or after missing observations. Regression tests cover ordering,
crossings, occlusion, low confidence, unknown/liveness transitions and re-entry. See the backend
README for installation and tracking options. The local SQLite session bridge, polling API, bounded events and processing measurement
hooks are now implemented. The separate Next.js/shadcn dashboard and simple CSV export are now implemented.
Volunteer portrait/academic metadata enrichment and real-camera trials remain pending. The findings below describe the pre-change audit.


## Scope

Real camera recognition, multi-face identification, automatic attendance, duplicate prevention, unknown handling, a single presentation dashboard, simple report output, and demo validation. Supporting academic/exam metadata may be simulated and must be labelled as such. No full administration platform or institutional integration.

## Existing implementation to retain

- `backend/app/vision/embedder.py`: InsightFace detection and embeddings for multiple faces.
- `backend/app/vision/matcher.py`: similarity threshold and separation from the next different identity.
- `backend/app/vision/attendance_flow.py`: overlapping-box face tracking and per-track match confirmation (three observations by default).
- `backend/app/vision/attend.py`: desktop camera loop, multiple-face processing, database attendance writes, OpenCV annotations and FPS.
- `backend/app/attendance.py`, `models.py`: attendance persistence and per-exam/student uniqueness, including duplicate insert handling.
- `backend/app/main.py`: exams, students and attendance API reads.
- `backend/app/vision/evaluate.py`: labelled still-image probes and threshold sweep; not a walking/crowd benchmark.
- Existing phone/desktop enrollment, manual inbox sync and cleanup commands.

## Findings and required changes

### 1. Recognition continuity and instrumentation (first priority)

The tracker is a greedy intersection-over-union box tracker, NOT ByteTrack despite the root README description. Fast movement, crossing faces, and occlusion may switch IDs. After a track is marked, `AttendanceDecider.observe` returns its old identity without checking subsequent matches. If a different person inherits that track, the overlay can show the old identity and the new person may not be marked. Expired track IDs also do not establish unique unknown-person identities.

Required:
- Add regression tests for crossing/overlapping boxes, changed detection order, missing observations, identity changes after confirmation, disappearance/re-entry, and simultaneous known/unknown faces.
- Invalidate/reconfirm identity when fresh observations contradict a confirmed track. Do not let attendance-write suppression freeze identity forever.
- Define consecutive-observation handling when frames are missed.
- Improve association if tests/recorded trials demonstrate failures; do not replace the recognizer or promise ByteTrack without implementing it.
- Add structured, timestamped recognition/session events instead of relying on display strings. Bound the in-memory event history (the current list grows indefinitely).
- Capture processing latency, processed FPS and visible face counts. FPS alone is not recognition accuracy or camera throughput.
- Distinguish model unavailable, no usable embedding, checking, unidentified, identified, already present, and attendance-write failure.

### 2. Local live-session bridge (new)

The camera loop and FastAPI currently run separately. Attendance rows expose successful writes only; unknown faces, checking states, camera health and recognition events never reach the API.

Required:
- Introduce a small session/event service connecting the recognition worker to the local API (an in-process worker or an explicit IPC bridge; a module global cannot connect two independent processes).
- Expose session snapshot/events with session ID, examination, camera/worker status, timestamps and bounded event IDs. Start with polling; SSE is optional.
- Report stopped/disconnected/error states accurately, and keep database attendance separate from session counters.
- One owner opens the attendance camera. Enrollment must not compete for it.
- Keep recognition and dashboard local to the PC for the offline demo. Netlify remains the phone intake site; a Netlify page cannot automatically access the PC's SQLite or camera worker.

Recommended counter definitions:
- Identified: distinct enrolled student numbers confirmed during this session.
- Present: saved attendance for the selected exam, explicitly labelled if it includes earlier runs.
- Unidentified now: currently visible stable unknown tracks, after a short grace period. Not a claim of unique unknown people.
- Optional unknown encounters: debounced track encounters, explicitly labelled; re-entry can count again.

### 3. Single dashboard (new frontend view)

`frontend/src/App.tsx` is enrollment only. Preserve that journey and add a separate local dashboard view.

Required:
- Exam/venue header; camera/worker running, stopped and error states.
- Real session counters, recent identified students and timestamped activity.
- Student detail panel: portrait when available, name, index, programme, department, level, exam, building/hall, recognition time and saved attendance status.
- Clear empty/loading/stale/error states; no fictional live counts.
- Optional live camera view if wanted for presentation. Reuse worker frames, do not open a second camera.
- Frontend tests with API fixtures, plus a real local end-to-end check.

### 4. Volunteer presentation data and portraits (small supporting change)

Student already has programme, level and nullable photo_path; Exam has course title, hall and times. Department/building are not separate fields. Web-created volunteers have placeholder programme/level, and web enrollment does not save a portrait for the dashboard.

Required:
- Use a small local demo metadata mapping keyed by exact student number for department/building and supporting details; schema expansion is not necessary just for presentation.
- Preserve actual volunteer names/index numbers and face identity mapping. Mark unverified academic details as demo metadata.
- Decide whether to keep one consented local enrollment portrait or supply a separate local profile image. Use a placeholder if absent; never substitute another person's face.
- Serve portraits through a constrained endpoint, not arbitrary filesystem paths. Keep biometric files ignored by Git.
- Use non-destructive preparation; do not reseed/reset the volunteer database.

### 5. Existing eligibility policy (scope decision)

`mark_attendance` still requires registration, cleared fees and no suspension. This can identify someone successfully but reject attendance, contrary to a simplified all-enrolled-volunteers demonstration.

Recommended first-demo approach: prepare selected volunteers as registered and eligible using existing tools, with no new fee/registration interface. Show identified and present separately if a rejection occurs. If the intended rule is instead 'every enrolled identity is automatically present', implement an explicit demo policy with tests rather than silently removing existing rules globally.

### 6. Simple report (new)

Add a CSV download for selected-exam saved attendance: name, index, examination, timestamp, source and confidence (label similarity as similarity, not probability). Reuse attendance reads, escape spreadsheet-formula values, and never export embeddings or raw photos. No complex reporting platform.

### 7. Validation and presentation (requires actual PC/camera)

The existing unit tests and still-image evaluator do not establish mass-entry performance. Run consented trials with ground truth:
- One person; sequential people; multiple simultaneous faces; crossing/occlusion.
- Short appearances, walking speeds, distance, different lighting and glasses.
- Known and unknown people together, and repeat appearances/re-entry.
- Offline operation after enrollment/sync and model download; correct exam writes; repeat runs without duplicate rows.

Record hardware, camera resolution, model/settings, volunteer count, simultaneous-face count, correct identifications, wrong identities, missed known people, unknown false accepts, duplicate rows, latency and processed FPS. Agree numerical acceptance criteria after an initial baseline, before declaring success. Compare attendance to a manually checked roster. Prepare backup recordings/screenshots with volunteers' consent.

## Suggested delivery order

1. Recognition regression tests, continuity fix, structured events and baseline measurement hooks.
2. Local session/API bridge and explicit counter definitions.
3. Single dashboard and student detail panel with local demo metadata/portraits.
4. CSV output and automated integration tests.
5. Real-camera trials, tuning, fixes and presentation rehearsal.

## Audit limitations

Source and existing tests were inspected. Tests were not run in this audit; project dependencies are not installed in this checkout. No real camera, live Netlify/Supabase settings, volunteer database or measured crowd-performance results were inspected. Application code remains unchanged.

## Validation preparation progress

Added `app.vision.validate_video`: read-only replay of consented clips through the
recognizer, ByteTrack and confirmation, scored against manually supplied face-box/identity
annotations. Reports observation-level errors, unresolved unknowns and replay processing
timing without changing attendance or publishing a live session. See `VALIDATION.md` for
the actual live multi-person rehearsal and the replay limitations. As of this change,
155 backend tests pass; actual PC/camera performance has not been measured here.

## Local demo control progress

Added a narrowly scoped local panel for camera start/stop, inbox sync, volunteer readiness,
registration and preview-confirmed selected/keep-only cleanup. This is not the full admin
platform excluded from the agreed scope. Windows startup convenience files and a private
backend env template are included. See dashboard/README.md for authentication boundaries,
cloud deletion exclusions, process lifecycle limits and one-time setup.

## Phone enrollment pose verification

Added same-origin MediaPipe worker/model assets and pose-gated capture. Holding still facing
forward cannot satisfy left/right steps; invalid/extra faces block saving and model failure
has no timed fallback. Payload/sync are unchanged. This remains browser guidance, not robust
liveness or trusted server-side pose validation. See frontend/README.md for thresholds,
compatibility, tests, asset provenance and actual-phone test requirements.

## Presentation enrichment

Added an explicit display-only CSC department mapping and 24 -> level 300 rule in
`app.presentation`, shared by the students API and camera overlay. Dashboard profiles,
student rows and a latest-record card show the separate display data. Original student
records and eligibility stay unchanged; unspecified year codes are not extrapolated.
Further proposed visual additions require user agreement (portraits, fullscreen presentation,
venue branding and session graphics); they are not implemented by this enrichment.

### Dashboard redesign follow-up

Replaced the green-accented workspace with the configured shadcn New York / Neutral
theme, semantic tokens, Table and keyboard-accessible Tabs. Preserved local controls,
live polling, explicit illustration mode and offline safeguards. The dashboard applies
the two agreed index display rules even against old/stale API responses; CSC/24 always
displays level 300 without changing the stored level. All other year codes keep supplied
levels. Phone enrollment and backend recognition behavior are unchanged by this redesign.

### Radix/teal iterative design review

Iteration 1 only: installed actual Radix Themes, root Theme and layered styles; native
Radix heading/statistic cards; applied the user's supplied seven-colour teal palette to
shared semantic tokens and sidebar. Layout, controls and recognition behavior preserved.
Await visual review before further layout/component migration or charts. The next proposed
increment is a single attendance-over-time chart using saved records, not synthetic trends.

### Charts and stronger colour — iteration 2

User approved proceeding: added Recharts cumulative saved attendance and saved-student
level breakdown with empty/offline states, minute aggregation, deduplication and invalid
stamp handling. Applied a saturated teal canvas/filled metric cards while keeping dense
records readable. No absent totals/percentages inferred. Await the next visual review
before adding more charts or changing the layout further.
