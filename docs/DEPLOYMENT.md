# Deploying the enrollment web app (free / low-cost)

This guide gets the **student-facing enrollment page** online so group members can open it on
their phones, type their name + index number, and do a face scan. It also covers connecting the
live attendance demo to the same data.

> **⭐ Recommended: the hybrid "Supabase inbox".** Members upload anytime (even with your PC off);
> your PC syncs and runs the full-accuracy model when you're online. No cloud RAM limits, no
> accuracy loss. See **[HYBRID_SYNC.md](HYBRID_SYNC.md)**. Paths A and B below are the alternatives.

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

The backend serves the **compiled** frontend from `frontend/dist`. Build it once first. From the
repository root in PowerShell:

```powershell
cd frontend
npm ci
npm run build
cd ../backend
uv run --frozen --extra vision uvicorn app.main:app --port 8000
```

Open `http://localhost:8000/` — it redirects to the enrollment app at `/app`. On the same machine
the camera works over `http://localhost`. To let *phones* reach it you need HTTPS, so use one of
the hosting options below (or a tunnel). Docker builds the frontend automatically.

For frontend-only development, run `npm run dev` in `frontend/` (Vite proxies API calls to
`http://127.0.0.1:8000`; override with `BACKEND_ORIGIN`).

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

### Accuracy: the hidden cost of the 512 MB free tier

`buffalo_s` isn't just "a bit lighter" — InsightFace's own published benchmarks show a real accuracy
drop, and it is **largest on African faces**, which matters for a group in Ghana:

| Benchmark (InsightFace model zoo) | `buffalo_l` | `buffalo_s` |
| --- | --- | --- |
| LFW (easy, frontal) | 99.83 | 99.70 |
| AgeDB-30 (age variation) | 98.23 | 96.58 |
| IJB-C E4 (hard, varied) | 97.25 | 95.02 |
| MR-ALL (all) | 91.25 | 71.87 |
| **MR-ALL (African subset)** | **90.29** | **69.45** |

On clean, frontal, well-lit shots the two are close (LFW). But on varied conditions — and especially
African faces — `buffalo_s` is substantially weaker. Source:
<https://github.com/deepinsight/insightface/tree/master/model_zoo>. If recognising your group reliably
in front of the class is the priority, prefer `buffalo_l`.

### Recommended for a class demo

- **⭐ Best overall — the hybrid "Supabase inbox":** members upload anytime (PC can be off), your PC
  syncs and runs full-accuracy `buffalo_l` when online. No cloud RAM limits, no accuracy loss, $0.
  See **[HYBRID_SYNC.md](HYBRID_SYNC.md)**.
- **Best accuracy + reliability, simplest hosting:** **Your PC + a tunnel** (Path B) with
  `buffalo_l`. No RAM limits, no cold starts, full-accuracy model. Trade-off: your PC stays on while
  people enroll. Use ngrok's free static domain so the link doesn't change between runs.
- **Fully online, $0, no card, PC can be off:** **Render free + Supabase** (Path A) with `buffalo_s`.
  Accept the accuracy drop above; reasonable only if the demo is controlled (good light, frontal,
  cooperative subjects).
- **Fully online + full accuracy (if you have a card):** **Google Cloud Run** (≥1 GB RAM) + Supabase
  with `buffalo_l`. The always-free quota covers a small demo; needs a Google Cloud billing account.

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

1. Build the frontend once (`cd frontend`, `npm ci`, `npm run build`) as in the local section above.
   Then start the app from `backend/`, pointing at Supabase if you want the data shared/persistent,
   or leave the default SQLite for a self-contained demo:

   ```powershell
   # Optional: shared database (install the postgres extra once: uv sync --extra postgres)
   $env:DATABASE_URL = "postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres"
   $env:ENROLL_DEFAULT_EXAM = "CS101"
   uv run --extra vision --extra postgres uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

   (Omit the `DATABASE_URL` line and the `--extra postgres` to use local SQLite instead.)

2. Expose it to phones over a free HTTPS tunnel. Pick one:

   **Option 1 — ngrok (recommended: a stable link).** Create a free account at <https://ngrok.com>,
   claim your one free static domain (Dashboard → Domains), then:

   ```powershell
   winget install --id Ngrok.Ngrok
   ngrok config add-authtoken <your-token>
   ngrok http --domain=<your-name>.ngrok-free.app 8000
   ```

   The URL `https://<your-name>.ngrok-free.app` stays the same every time you run it, so you can
   share it with the group once. (Free ngrok shows a brief "visit site" interstitial to visitors.)

   **Option 2 — Cloudflare quick tunnel (no account, but the link changes each run):**

   ```powershell
   winget install --id Cloudflare.cloudflared
   cloudflared tunnel --url http://localhost:8000
   ```

   It prints a random `https://<random>.trycloudflare.com` URL. Fine for a one-off; re-share it if
   you restart. A *named* Cloudflare tunnel gives a stable URL but needs your own domain.

3. Run attendance on the same PC (same database, same `buffalo_l` model — the default):

   ```powershell
   uv run --extra vision python -m app.vision.attend --exam CS101
   ```

> Keep the PC awake while people enroll (Windows: Settings → System → Power & sleep → set Screen and
> Sleep to a long timeout or Never when plugged in). The tunnel and the app must both stay running.

---

## Environment variables (reference)

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///backend/data/exam_attendance.db` | Database. Use Supabase `postgresql+psycopg://…` when hosted. |
| `ENROLL_MODEL` | `buffalo_l` | InsightFace pack for web enrollment. Use `buffalo_s` on 512 MB hosts. Must match attendance. |
| `ENROLL_DEFAULT_EXAM` | _(none)_ | If set (e.g. `CS101`), every web enrollee is auto-registered for that exam. |
| `CORS_ORIGINS` | `*` | Comma-separated allowed browser origins, or `*`. Needed only if the frontend is hosted separately from the API. |
| `PORT` | `7860` (Docker) | Port the server binds to. Render/Koyeb inject their own; the Dockerfile honors it. |

## If you host the frontend separately (Netlify / static hosts)

The recommended separate host is the **hybrid Supabase inbox** — see
[HYBRID_SYNC.md](HYBRID_SYNC.md). Netlify then needs no face model and no running API.

**Git-connected Netlify:** the root `netlify.toml` builds `frontend/` (`npm ci && npm run build`)
and publishes `dist` on Node 22. Set `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` (public
anon/publishable only), and optionally `VITE_ENROLL_EXAM` in the site's environment variables, then
deploy. Do not upload the source folder as a static site.

**Drag & drop:** run `npm ci` and `npm run build` in `frontend/`, then upload **`frontend/dist`**.
Without build-time variables, fill in `frontend/public/config.js` before building; it is copied to
`dist/config.js` as an optional runtime override.

**Direct API mode instead of the inbox:** leave the Supabase variables empty and set
`VITE_API_BASE` to your backend URL (e.g. `https://<name>.onrender.com`), plus `VITE_ENROLL_EXAM`
if wanted. Set `CORS_ORIGINS` on the backend to the frontend origin. The backend must stay awake
and have enough RAM for the enrollment model, so this is not the recommended free Netlify setup.

After changing environment variables, trigger a new Netlify deploy. If the page still shows the
old spinner, check that the latest deploy published the built `dist` and clear the browser cache.

## Caveats checklist before the demo

- [ ] Supabase project is **awake** (Restore it if paused).
- [ ] Host URL opened ~1 min early (free tiers cold-start).
- [ ] Enrollment model = attendance model (`buffalo_s` ↔ `--model buffalo_s`, or `buffalo_l` ↔ default).
- [ ] Everyone enrolls with the **same** model the attendance demo will use.
- [ ] Phones use the **https://** URL (camera won't start on plain http).
