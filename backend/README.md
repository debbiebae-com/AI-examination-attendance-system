# Backend

FastAPI + SQLAlchemy + SQLite. Managed with `uv`.

## Setup

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

## Notes

- Attendance times are stored as UTC. Ghana (Accra) is UTC+0 year-round, so no conversion is needed for display.
- Duplicate attendance is blocked twice: a check in `mark_attendance()` and a unique constraint on `(exam_id, student_id)` in the database.
