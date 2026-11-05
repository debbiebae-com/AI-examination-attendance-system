# Backend

FastAPI + SQLAlchemy + SQLite. Managed with `uv`.

## Setup

The project uses Python 3.12 (pinned in `.python-version`). Python 3.15 has no `onnxruntime` build yet.

```bash
cd backend
uv sync                      # creates .venv and installs dependencies
uv run python -m app.seed    # seeds 20 simulated students, 2 exams, registrations
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Swagger UI: http://localhost:8000/docs
- Reseed from scratch: `uv run python -m app.seed --reset`
- Tests: `uv run pytest`

> If PowerShell says `'uv' is not recognized`, see [../docs/TROUBLESHOOTING.md](../docs/TROUBLESHOOTING.md)
> — it's a one-minute PATH fix, not a project problem.

## Simulated data

The demo uses fictional students (`UGS-26-001` to `UGS-26-020`) and two exams on 10 Nov 2026.

| Student | Situation |
|---|---|
| UGS-26-013 | Registered, but fees not cleared (refused) |
| UGS-26-015 | Registered, but suspended (refused) |
| UGS-26-016 to 020 | Registered for MTH201 only |
| UGS-26-001 to 005 | Have synthetic enrollment photos in `data/demo_photos/` |

Eligibility rules live in `app/eligibility.py`: registered for the exam, fees cleared, and not suspended. They are simulated and should be replaced with the school's real rules.

## Layout

```
app/
  config.py       settings (DATABASE_URL, paths)
  db.py           engine and session dependency
  models.py       Student, Exam, Registration, AttendanceRecord
  eligibility.py  pure eligibility rules
  attendance.py   mark_attendance(): eligibility check and duplicate prevention
  seed.py         simulated data
  main.py         REST API
data/demo_photos/ synthetic enrollment photos (fictional people)
tests/            pytest suite
```

## Face recognition (vision extra)

Recognition uses InsightFace's `buffalo_l` model: SCRFD for face detection and ArcFace for embeddings. It is optional, so the API and tests run without it.

On your PC, from `backend/`:

```bash
uv sync --extra vision
uv run --extra vision python -m app.vision.spike
```

Always add `--extra vision` to `uv run` for vision commands. A plain `uv run` re-syncs the environment to the default packages and removes InsightFace and OpenCV.

The first run downloads `buffalo_l` (about 300 MB) from GitHub to `~/.insightface`. The spike then:

1. Enrolls the five demo photos. Each photo must contain exactly one face.
2. Matches each photo back against the enrolled gallery. Each should match its own student.

Matching settings are in `app/vision/matcher.py`. `DEFAULT_THRESHOLD = 0.40` and `DEFAULT_MARGIN = 0.05` are starting values. Tune them on real camera footage before the demo. You can also override them with `--threshold` and `--margin`.

Notes on the vision dependencies:

- The extra uses InsightFace 2.1, which installs from a pre-built wheel. InsightFace 0.7.3 must compile C++ code, which needs Microsoft's C++ Build Tools on Windows.
- Model weights are for non-commercial research use only (see the project's licensing note).

## Guided capture (desktop, with liveness)

This is the Instagram-style enrollment: a window shows the camera with prompts. It asks the person to look straight, then turn left, then turn right. Only frames that match each prompt are kept, and a photo or screen is refused by the liveness check.

```bash
uv run --extra vision python -m app.vision.capture --student-no VOL-001 --name "Ama Mensah" --exam CS101
```

- `--name` is needed only when the student number is new. A new student is created as a test volunteer.
- `--exam` registers the student for an exam, so attendance will accept them.
- Run it again to replace the student's capture.
- Press `q` or `Esc` to cancel.

It is built for a smooth, low-retry experience:

- **Left/right always match the person.** The preview is mirrored (selfie-style) and head angles are converted to *person space*, so "turn to your LEFT" means the person's own left. On-screen arrows point the right way, a yaw gauge shows the target zone, and turning the wrong way gets an explicit correction ("That's your RIGHT. Turn to your LEFT"). There is no sign flag to get wrong. If left/right ever feels inverted (some phone-as-webcam apps already mirror their feed), press **`m`** in the window to flip the mirror — no restart needed.
- **Fast preview.** Each camera frame runs only the cheap detector + landmarks. The heavy face embedding and liveness check run on a worker thread for the few kept frames, and a background camera reader always shows the newest frame (no stale-frame lag). A live `fps` readout is shown top-right.
- **Fewer retries.** The head angle is smoothed and gentle "move closer / back / center" guidance keeps the face usable. There is no blink step.
- **Liveness from the turn challenge.** Turning left and right is the active liveness proof — a photo or screen cannot turn its head. The passive liveness model is **optional and off by default**, because it is unreliable on some cameras and lighting and was rejecting real faces. Turn it on with `--liveness`; when on, its vote is aggregated over the kept frames (a clear majority of live votes passes) rather than rejecting single frames.

Options:

- `--camera 1` if the wrong camera opens.
- `--no-mirror` if the camera feed is *already* mirrored (some phone-as-webcam apps mirror internally). The arrows and yaw gauge flip with it, so left/right stay correct.
- `--det-size 320` guidance detector resolution. Lower is faster; raise it if faces are small in the frame.
- `--threads N` onnxruntime CPU threads, if you want to cap CPU use.
- `--samples 3` frames kept per straight/turn step.
- `--liveness` enable the passive liveness model (off by default).

Tuning constants live in `app/vision/capture_flow.py`: `TURN_MIN_DEG` and `STRAIGHT_MAX_DEG` (turn angles).

When `--liveness` is used, the passive check uses InsightFace's optional add-on model (`liveness.onnx`, about 1.5 MB), downloaded on first use to `~/.insightface/addons`. The model's license is the same non-commercial research terms as `buffalo_l`. Without `--liveness`, the add-on is not loaded at all.

## Registering students for an exam

A student is only recorded as present if they are **enrolled** (have face samples), **registered for the exam**, fees cleared, and not suspended. Capture with `--exam` registers automatically. To register or check afterwards without re-running capture:

```bash
uv run python -m app.register --exam CS101 --student-no VOL-001 VOL-002 VOL-003
uv run python -m app.register --exam CS101 --list
```

`--list` prints a table of everyone registered or enrolled, showing their registration, face-sample count, and eligibility — so you can confirm the volunteers are ready before running attendance.

## Web enrollment (phones)

The student-facing web app (`frontend/`, served at `/app`) lets group members enroll from their
phones: they enter their **name + index number**, then capture 3 photos (look straight, turn left,
turn right). The backend computes the face embeddings with the same model used for attendance and
stores them. No desktop capture needed for these volunteers.

```bash
uv run --extra vision uvicorn app.main:app --host 0.0.0.0 --port 8000
# open http://localhost:8000/  -> redirects to the enrollment app at /app
```

- `POST /enroll` accepts `{full_name, student_no, photos:[{step, image(base64)}], exam?}`. Each photo
  must contain exactly one face; at least one usable photo is required (3 gives the best matching).
- Set `ENROLL_DEFAULT_EXAM=CS101` to auto-register every web enrollee for the demo exam, or pass
  `exam` per request. Otherwise register later with `app.register`.
- `GET /students` now includes a `face_samples` count so you can confirm who has enrolled.
- Web samples are stored with a `web:` source prefix (desktop capture uses `capture:`); both are
  used by the matcher.
- **Model must match attendance.** `ENROLL_MODEL` (default `buffalo_l`) sets the server's model. On a
  512 MB free host use `buffalo_s`, and run attendance with `--model buffalo_s`.
- To put it online for phones (HTTPS is required for the camera), see
  [../docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md).

### Hybrid sync (members upload anytime, PC embeds when online)

Instead of running the model in the cloud, the web app can store submissions in a Supabase "inbox"
(name + index + raw photos). Members submit even when your PC is off; you sync later and compute the
full-accuracy embeddings locally:

```bash
# on your PC, with SUPABASE_URL and SUPABASE_SERVICE_KEY set
uv run --frozen --extra vision python -m app.sync            # pull pending, embed, save, mark synced
uv run --frozen --extra vision python -m app.sync --dry-run  # just list what's pending
```

Sync wipes the cloud photos after processing (privacy) and is safe to re-run. Setup walkthrough:
[../docs/HYBRID_SYNC.md](../docs/HYBRID_SYNC.md).

## Live attendance (desktop)

This recognises enrolled students in the camera view and records them as present for an exam:

```bash
uv run --extra vision python -m app.vision.attend --exam CS101
```

- Each face must match the same student for 3 frames in a row before attendance is recorded.
- Several students can be recognised at once. Each face is tracked from frame to frame.
- Students who aren't registered for the exam (or fail eligibility) are shown in red and not recorded.
- Students already marked for the exam show as "already marked". The database blocks duplicates.
- A background camera reader keeps the preview on the newest frame, with a live `fps` readout.
- Press `q` to stop.

Options:

- The passive liveness model is **off by default** (unreliable on some cameras). Add `--liveness` to require it; then a face must also pass liveness before being recorded.
- `--det-size 640` detector resolution. Lower (e.g. 480 or 320) is faster but may miss distant faces.
- `--model buffalo_l` InsightFace pack. **Must match the enrollment model** — if the web server used
  `ENROLL_MODEL=buffalo_s`, pass `--model buffalo_s` here.
- `--threads N` onnxruntime CPU threads.
- `--threshold` and `--margin` tune matching (see the accuracy test below). `--confirm` sets how many frames a match must hold.

## Accuracy test on real photos

The demo photos are AI-generated and can't show how well matching separates people. Use real photos from consenting volunteers instead. Keep them on your PC: they're biometric data and `backend/data/probes/` is excluded from Git.

Create the folders by running the evaluator once:

```bash
uv run --extra vision python -m app.vision.evaluate
```

Then fill them in:

- `data/probes/reference/<Name>.jpg`: one clear photo per enrolled volunteer. The file name is the label.
- `data/probes/genuine/<Name>/*.jpg`: 3 to 4 other photos of the same volunteer, with different lighting, angles, and glasses.
- `data/probes/strangers/*.jpg`: photos of people who are not enrolled.

Run it again. It prints each photo's outcome and a threshold sweep, showing how often enrolled people are accepted and how often strangers are wrongly accepted.

## Notes

- Attendance times are stored as UTC. Ghana (Accra) is UTC+0 year-round, so no conversion is needed for display.
- Duplicate attendance is blocked twice: a check in `mark_attendance()` and a unique constraint on `(exam_id, student_id)` in the database.
