# Runs the FastAPI API + the student web app as ONE service.
# Works on Hugging Face Spaces (Docker, port 7860), Render, Fly.io, or any Docker host.
FROM python:3.12-slim

# OpenCV runtime libraries (insightface pulls opencv-python, which needs these).
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# InsightFace caches models under $HOME/.insightface. Pin HOME to a world-readable path
# so the weights baked in at build time are found at runtime, even as a non-root user.
ENV HOME=/app
WORKDIR /app

# Install dependencies from pyproject.toml (core + vision + postgres) without needing a
# package build backend. tomllib is in the standard library on Python 3.11+.
COPY backend/pyproject.toml /tmp/pyproject.toml
RUN python - <<'PY'
import tomllib
d = tomllib.load(open("/tmp/pyproject.toml", "rb"))
deps = (
    d["project"]["dependencies"]
    + d["project"]["optional-dependencies"]["vision"]
    + d["project"]["optional-dependencies"]["postgres"]
)
open("/tmp/requirements.txt", "w").write("\n".join(deps) + "\n")
PY
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Pre-download the face model at BUILD time so the first request isn't a long cold start.
# Override with --build-arg ENROLL_MODEL=buffalo_s for low-RAM hosts (must match attendance).
ARG ENROLL_MODEL=buffalo_l
ENV ENROLL_MODEL=${ENROLL_MODEL}
RUN python -c "from insightface.app import FaceAnalysis; FaceAnalysis(name='${ENROLL_MODEL}', providers=['CPUExecutionProvider']).prepare(ctx_id=-1)" \
    && chmod -R a+rX /app/.insightface

# Application code.
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# SQLite (default) writes here; make it writable for non-root runtimes (HF Spaces uid 1000).
RUN mkdir -p /app/backend/data && chmod -R a+rwX /app/backend/data

WORKDIR /app/backend

# HF Spaces expects 7860; Render injects $PORT. Default to 7860.
ENV PORT=7860
EXPOSE 7860

# Initialize schema + demo data (idempotent), then serve API + web app.
CMD python -m app.seed && python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
