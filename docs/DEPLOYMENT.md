# Deploying the enrollment web app (free / low-cost)

This guide gets the **student-facing enrollment page** online so group members can open it on
their phones, type their name + index number, and do a face scan. It also covers connecting the
live attendance demo to the same data.

## How it fits together

```
Phone browser ──HTTPS──> One FastAPI server
                          ├── serves the web app at  /app
                          └── POST /enroll  → runs InsightFace → stores face embeddings
                                                    │
                                          Database (SQLite locally,
                                          or Supabase Postgres when hosted)
                                                    │
Desktop attendance (attend.py) ─────────────────────┘  reads the same embeddings
```

**Two rules that matter:**

1. **The face model runs on the server, not in the phone.** Embeddings must come from the *same*
   InsightFace/ArcFace model used by attendance, so the phone only uploads photos and the Python
   backend computes the embeddings.
2. **The enrollment model and the attendance model must match.** If the server enrolls with
   `buffalo_s`, attendance must run with `--model buffalo_s` (and vice-versa for `buffalo_l`).
   Mixing models produces embeddings that will not match.

**Phones need HTTPS.** Browsers only allow camera access (`getUserMedia`) on a secure origin.
Every host below gives you an `https://` URL automatically. `http://localhost` is the only
non-HTTPS exception (fine for testing on the same machine).

---

## Try it locally first (no hosting needed)

From `backend/`:

```powershell
uv run --extra vision uvicorn app.main:app --port 8000
```

Open `http://localhost:8000/` — it redirects to the enrollment app at `/app`. On the same machine
the camera works over `http://localhost`. To let *phones* reach it you need HTTPS, so use one of
the hosting options below (or a tunnel).

---

## Free hosting in 2026 — the honest picture

| Option | Cost | RAM | Notes |
| --- | --- | --- | --- |
| **Your PC + Cloudflare Tunnel** | Free | Your PC's RAM | Most reliable. Runs `buffalo_l` full quality. PC must stay on while enrolling. |
| **Render (free web service)** | Free | 512 MB | No card for most. Sleeps after 15 min idle (~1 min wake). Use `buffalo_s`. |
| **Koyeb (free web service)** | Free | 512 MB | Usually no card. Scales to zero after ~1 h. Use `buffalo_s`. |
| **Google Cloud Run** | Free tier | up to 1 GB+ | Needs a Google Cloud billing account (card). Can run `buffalo_l`. |
| **Supabase (database only)** | Free | 500 MB Postgres | Pauses after 7 days idle (unpause before the demo). Cannot run the face model. |
| **Hugging Face Spaces (Docker)** | **PRO $9/mo to create** | 16 GB | As of 2026, creating Docker/Gradio Spaces needs a paid plan; also blocks outbound port 5432, so it cannot reach Supabase. Not recommended here. |

> **RAM is the deciding factor.** `buffalo_l` (the high-accuracy pack) needs roughly 0.7–1 GB+ and
> will **not** fit in a 512 MB free instance. `buffalo_s` (a smaller pack) fits in 512 MB. So on
> Render/Koyeb free, enroll **and** run attendance with `buffalo_s`. On your PC or Cloud Run you can
> use `buffalo_l`.

### Recommended for a class demo

- **Want it fully online with zero cost and no PC left on?** → **Render free + Supabase**, using
  `buffalo_s`. Follow "Path A" below.
- **Want the best accuracy and reliability, and don't mind leaving your PC on?** → **Your PC +
  Cloudflare Tunnel**, using `buffalo_l`. Follow "Path B". This avoids all RAM/sleep limits.

---

## Set up Supabase (shared persistent database) — used by both paths

A hosted server's local disk is ephemeral (data is lost on restart), and you want the phone
enrollments to reach the desktop attendance demo. A shared Postgres solves both. Supabase's free
tier is plenty for a class.

1. Create a project at <https://supabase.com> (free, no card). Pick a region close to you.
2. Wait for it to provision, then open **Project Settings → Database → Connection string**.
3. Copy the **Session pooler** string (host looks like `aws-0-<region>.pooler.supabase.com`, port
   `5432`). The session pooler works over IPv4 and supports SQLAlchemy. It looks like:

   ```
   postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
   ```

4. Convert it for this app by changing the scheme to `postgresql+psycopg://`:

   ```
   postgresql+psycopg://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
   ```

   This is your `DATABASE_URL`. Keep the password secret — set it as an environment variable on the
   host, never commit it.

> The direct connection (`db.<ref>.supabase.co:5432`) is IPv6-only on the free tier; the **pooler**
> string above is the one to use. If the project pauses after 7 idle days, open the Supabase
> dashboard and click **Restore** before your demo.

---

## Path A — Render free + Supabase (fully online, $0)

1. Push this repository to GitHub (already done if you're reading this there).
2. In Supabase, get your `DATABASE_URL` (above).
3. On <https://render.com> → **New → Web Service** → connect the repo.
   - **Runtime:** Docker (Render auto-detects the `Dockerfile`).
   - **Instance type:** Free.
   - A `render.yaml` blueprint is included, so you can also use **New → Blueprint**.
4. Set environment variables:

   | Key | Value |
   | --- | --- |
   | `DATABASE_URL` | your Supabase `postgresql+psycopg://…` string |
   | `ENROLL_MODEL` | `buffalo_s` |
   | `ENROLL_DEFAULT_EXAM` | `CS101` (auto-registers every enrollee for the demo exam) |
   | `CORS_ORIGINS` | `*` (default; fine for a demo) |

   `ENROLL_MODEL` is also a Docker build arg, so the image pre-downloads `buffalo_s` at build time.
5. Deploy. Render gives you `https://<name>.onrender.com`. Opening it redirects to `/app`.
6. Share that URL with the group. Each person opens it on their phone, enters name + index number,
   and captures the 3 photos. Their data lands in Supabase.

**Run attendance against the same data (on your PC):**

```powershell
$env:DATABASE_URL = "postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres"
uv run --extra vision --extra postgres python -m app.vision.attend --exam CS101 --model buffalo_s
```

The `--model buffalo_s` is essential — it must match the server's `ENROLL_MODEL`.

> First load after idle takes ~1 minute (Render free spins down). Open the URL a minute before you
> need it. If `buffalo_s` ever runs out of memory on the free instance, move to Path B or Cloud Run.

---

## Path B — Your PC + Cloudflare Tunnel (free, full accuracy)

This runs the real `buffalo_l` model on your PC and exposes it to phones over a free HTTPS tunnel.
No RAM limits, no cold starts. Your PC must stay on while people enroll.

1. Start the app (from `backend/`), pointing at Supabase if you want the data shared/persistent,
   or leave the default SQLite for a self-contained demo:

   ```powershell
   # Optional: shared database (install the postgres extra once: uv sync --extra postgres)
   $env:DATABASE_URL = "postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres"
   $env:ENROLL_DEFAULT_EXAM = "CS101"
   uv run --extra vision --extra postgres uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

   (Omit the `DATABASE_URL` line and the `--extra postgres` to use local SQLite instead.)

2. Install Cloudflare's tunnel tool (`cloudflared`) and run a quick tunnel:

   ```powershell
   winget install --id Cloudflare.cloudflared
   cloudflared tunnel --url http://localhost:8000
   ```

   It prints a URL like `https://<random>.trycloudflare.com`. That is an HTTPS address phones can
   open. Share it; it forwards to your PC's app at `/app`.

3. Run attendance on the same PC (same database, same `buffalo_l` model — the default):

   ```powershell
   uv run --extra vision python -m app.vision.attend --exam CS101
   ```

> Quick-tunnel URLs are temporary and change each run — fine for a demo. For a stable URL, create a
> named tunnel in the Cloudflare dashboard (still free). `ngrok http 8000` is an alternative.

---

## Environment variables (reference)

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///backend/data/exam_attendance.db` | Database. Use Supabase `postgresql+psycopg://…` when hosted. |
| `ENROLL_MODEL` | `buffalo_l` | InsightFace pack for web enrollment. Use `buffalo_s` on 512 MB hosts. Must match attendance. |
| `ENROLL_DEFAULT_EXAM` | _(none)_ | If set (e.g. `CS101`), every web enrollee is auto-registered for that exam. |
| `CORS_ORIGINS` | `*` | Comma-separated allowed browser origins, or `*`. Needed only if the frontend is hosted separately from the API. |
| `PORT` | `7860` (Docker) | Port the server binds to. Render/Koyeb inject their own; the Dockerfile honors it. |

## If you host the frontend separately (optional)

The simplest setup serves the page from the same FastAPI server (`/app`), so no CORS or extra
hosting is needed. If you'd rather put the static page on Netlify/Vercel/Cloudflare Pages:

1. Upload the `frontend/` folder.
2. Edit `frontend/config.js`: set `API_BASE` to your backend URL (e.g.
   `https://<name>.onrender.com`) and optionally `EXAM`.
3. Set `CORS_ORIGINS` on the backend to the frontend's origin (or leave `*` for a demo).

## Caveats checklist before the demo

- [ ] Supabase project is **awake** (Restore it if paused).
- [ ] Host URL opened ~1 min early (free tiers cold-start).
- [ ] Enrollment model = attendance model (`buffalo_s` ↔ `--model buffalo_s`, or `buffalo_l` ↔ default).
- [ ] Everyone enrolls with the **same** model the attendance demo will use.
- [ ] Phones use the **https://** URL (camera won't start on plain http).
