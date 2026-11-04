# AI-examination-attendance-system

An AI-powered examination attendance system that uses real-time facial recognition (InsightFace, SCRFD, ByteTrack) to mark students present as they enter an exam hall, with a Next.js dashboard for invigilators and administrators.

## Repository layout

- `backend/`: FastAPI + SQLAlchemy + SQLite API (see [backend/README.md](backend/README.md))
- `frontend/`: Next.js dashboard (planned)
- `docs/`: architecture and demo notes (planned)

## Status

The data layer and REST API are in place using simulated students, exams and eligibility rules. Face recognition and the dashboard are next.

## Licensing note

InsightFace's pretrained weights are restricted to non-commercial research under their current terms. This project is intended for academic demonstration subject to those terms.

