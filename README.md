# AI-examination-attendance-system

An AI-powered examination attendance system that uses real-time facial recognition (InsightFace, SCRFD, ByteTrack) to mark students present as they enter an exam hall, with a Next.js dashboard for invigilators and administrators.

## Repository layout

- `backend/`: FastAPI + SQLAlchemy API, face recognition and web enrollment (see [backend/README.md](backend/README.md))
- `frontend/`: mobile-first student enrollment web app (static HTML/CSS/JS, served by the backend at `/app`)
- `docs/`: deployment and demo notes (see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md))
- `Dockerfile`, `render.yaml`: one-container deployment of the API + web app

## Status

The data layer, REST API, guided face capture, live attendance and **phone-based web enrollment**
are in place. Group members open the web app on their phones, enter their name + index number, and
do a 3-pose face scan; the backend computes the embeddings with the same model used for attendance.

## Enrollment web app

Run the backend and open `http://localhost:8000/` (redirects to `/app`). To put it online for phones,
see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — it covers free hosting (Render/Koyeb + Supabase, or a
Cloudflare tunnel from your PC) and the model/RAM trade-offs.

## Licensing note

InsightFace's pretrained weights are restricted to non-commercial research under their current terms. This project is intended for academic demonstration subject to those terms.

