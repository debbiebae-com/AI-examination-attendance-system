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
