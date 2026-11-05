# AI-examination-attendance-system

An AI-powered examination attendance system that uses real-time facial recognition (InsightFace, SCRFD, ByteTrack) to mark students present as they enter an exam hall, with a mobile student enrollment app and offline desktop attendance.

## Repository layout

- `backend/`: FastAPI + SQLAlchemy API, face recognition and web enrollment (see [backend/README.md](backend/README.md))
- `frontend/`: mobile-first student enrollment app (React + Vite + TypeScript + Tailwind + shadcn/ui; built to `frontend/dist` and served by the backend at `/app`)
- `docs/`: deployment and demo notes (see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md))
- `Dockerfile`, `render.yaml`: one-container deployment of the API + web app

## Status

The data layer, REST API, guided face capture, live attendance and **phone-based web enrollment**
are in place. Group members open the web app on their phones, enter their name + index number, and
do a 3-pose face scan; the backend computes the embeddings with the same model used for attendance.

## Enrollment web app

Build once with `cd frontend`, `npm ci`, `npm run build`; then run the backend and open
`http://localhost:8000/` (redirects to `/app`). Netlify and Docker build the frontend automatically.
To put it online for phones, see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

**Recommended: the hybrid "Supabase inbox"** ([docs/HYBRID_SYNC.md](docs/HYBRID_SYNC.md)) — group
members upload their name + index number + face photos anytime (even with your PC off), and your PC
syncs and computes the full-accuracy embeddings when you're online. No cloud RAM limits, no accuracy
loss, $0.

## Licensing note

InsightFace's pretrained weights are restricted to non-commercial research under their current terms. This project is intended for academic demonstration subject to those terms.

