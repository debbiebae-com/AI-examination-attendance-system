# Real-camera validation and rehearsal

This procedure produces evidence; it does not certify performance before testing.
Use consenting volunteers and keep videos/labels/reports local under
`backend/data/validation/` (ignored by Git). Do not upload recordings of students here.

## 1. Live trial first

Start the API, attendance and dashboard as described in `dashboard/README.md`.
Use the same recognition model used for enrollment (`buffalo_l` by default).
Do not reseed/reset the volunteer database. Before each trial note existing saved
attendance; a new camera session does **not** erase earlier attendance for that exam.
Use `app.register --exam CS101 --list` to check that your actual volunteers have face
samples and are eligible. Do not use fictional seeded portraits as evidence of accuracy.

Prepare at least three consenting enrolled volunteers and one consenting person who is
not enrolled. Use a paper roster as ground truth. Give each trial a name and record:

| Trial | What to do | What to inspect |
|---|---|---|
| Single entry | Each volunteer walks in separately | Correct name/index and one saved record |
| Sequential | Volunteers follow one another at normal spacing | No missed or swapped identities |
| Simultaneous | Two, then three people visible together | Independent correct identities |
| Crossing | Two people cross paths, briefly occlude one another | No stale name sticking to another face |
| Brief/fast | Repeat at different walking speeds | Missed entries, time to confirmation |
| Mixed | Enrolled and unknown people appear together | Unknown never marked as an enrolled student |
| Re-entry | Previously marked volunteer leaves and returns | Present count does not increase again |
| Lighting | Repeat with daylight, indoor and backlighting | Missed matches and wrong matches |
| Offline | Disconnect internet after model/enrollment sync | Recognition, API and dashboard keep working |
| Stop/recover | Press q, restart; separately stop/restart API | Truthful stopped/disconnected states |

Record your CPU/RAM, camera position/resolution, simultaneous face count, command settings,
correct entries, wrong identities, missed enrolled entries, unknown false accepts, visible FPS,
recognition delay and actual attendance row count. Unknown tracks are **not unique people**;
judge unknown-person outcomes using your manually observed trial, not that dashboard counter.

Choose acceptance criteria **before the final rehearsal**. A sensible safety rule is no
wrong-identity attendance and no duplicate rows in these trials. Also agree your required
walking speed, crowd size, acceptable missed-entry rate and recognition delay. Do not claim
support for a crowd size or lighting condition you have not tested.

The camera window currently runs the live video; the Next.js dashboard shows results, not a
second camera feed. Stop recognition before recording a separate test clip with another app,
so two programs do not fight over the webcam.

## 2. Optional repeatable recorded-video evaluation

The validator runs the same detector/recognizer, ByteTrack and identity confirmation on a
saved video. It reads your existing enrollment gallery, but **does not write attendance,
change students or publish a live session**. It is useful for comparing settings consistently.

### Prepare a short clip and ground truth

Save a consented clip as `backend/data/validation/entry.mp4`. Record labels for selected
frames in a JSON file at `backend/data/validation/labels.json`. Frame numbers are zero-based.
Every visible face in a labelled frame must have a pixel bounding box in the **original
unmirrored video**. Pause the clip in an annotation/video tool that shows frame number and
pixel coordinates; do not guess labels from the recognizer's own outputs.

Example format (replace these illustrative frame numbers, boxes and index with your clip's
actual ground truth; `null` means a genuinely non-enrolled person):

```json
{
  "frames": [
    {"frame": 30, "faces": [
      {"bbox": [100, 80, 200, 210], "student_no": "PS/CSC/24/0016"},
      {"bbox": [350, 90, 450, 220], "student_no": null}
    ]},
    {"frame": 60, "faces": []}
  ]
}
```

Do not annotate only successful/clear detections. Include early appearances, fast movement,
occlusion, mixed groups, empty scenes and difficult lighting. A known person's label must
match an actual enrolled index, not a fictional replacement name. Never label an enrolled
person `null` just because a particular frame was not recognized.

### Run from backend

```powershell
uv run --frozen --extra vision python -m app.vision.validate_video --video data/validation/entry.mp4 --annotations data/validation/labels.json --output data/validation/report-480.json
```

Defaults retain the tested attendance settings: `buffalo_l`, detector size 480, four threads,
threshold 0.40, margin 0.05, three consecutive identity matches. ByteTrack uses its attendance
defaults and low-confidence detector floor 0.1. Optional overrides: `--det-size`, `--threads`,
`--threshold`, `--margin`, `--confirm`, `--model` (must match enrollment).
Choose a new output name per run; input files and existing reports are not overwritten.

### Interpret the report correctly

- `known_correct`, `known_wrong_identity`, `known_not_identified`: outcomes per labelled
  known-face observation **after confirmation**, not per independent student.
- `unknown_false_accepts`: a labelled unknown assigned an enrolled identity.
- `unknown_correct_rejects`: a detected/tracked unknown explicitly classified unknown.
- `unknown_unresolved`: missing/untracked/checking/no-embedding/not-live faces; these are
  **not** counted as successful unknown rejections.
- `missed_face_detections`: labelled boxes without a prediction overlapping at least IoU 0.5.
- `unlabelled_detections`: predictions without a labelled box; may be detection errors or
  incomplete annotations—review the labels rather than assuming one or the other.
- `simulated_unique_marks`, `repeat_confirmations`: in-memory confirmation/deduplication
  results. **Not proof of eligibility or actual attendance database behavior.**
- `replay_processed_fps`, mean/p95 processing milliseconds: measured replay processing,
  including recognition/tracking but not model startup. Not camera/display FPS.
- Rates are `null` if there are no relevant known/unknown labels, not a misleading 100%.

Replay processes **every decoded frame**. Live attendance drops stale camera frames to
avoid lag; therefore replay can provide more consecutive evidence than the live system.
Replay success does not replace the live walking/crowd trial or prove real-time performance.
The validator uses matching/box logic, not a separate face-recognition model. Synthetic unit
tests verify the measurement logic; only your volunteer footage can provide measured accuracy.

## 3. Presentation evidence

Keep a simple trial sheet and export saved attendance from the live dashboard. Record a
consented short backup demonstration and take screenshots of actual results. If presenting
fictional layout preview data, leave its illustration banner visible. Explain the local/hybrid
architecture, the tested limits and false-match/missed-entry outcomes honestly.
