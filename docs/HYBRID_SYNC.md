# Hybrid sync: members upload anytime, your PC embeds when online

This is the recommended setup for your group. It solves the one thing you can't control — *when*
each member is ready to upload — without sacrificing accuracy.

## The idea

```
Member's phone (anytime)                 Your PC (when you're online)
┌──────────────────────┐                ┌────────────────────────────────┐
│ Web app (static host)│                │  python -m app.sync            │
│ name + index + frames│──insert──┐    │   1. pull pending submissions   │
└──────────────────────┘          │    │   2. run buffalo_l  (full acc.) │
                                  ▼    │   3. save to local SQLite       │
                     ┌─────────────────┴─┐ 4. mark synced, wipe photos  │
                     │ Supabase "inbox"  │◀────────────────────────────┘
                     │ (always on, free) │
                     └───────────────────┘          │
                                                    ▼
                                          attend.py  (fully offline)
```

- **No face model runs in the cloud.** Supabase just *holds* the raw photos + details. So there's no
  512 MB RAM problem and no `buffalo_s` accuracy drop.
- **Your PC does the recognition** with the full-accuracy `buffalo_l` model when you sync.
- **Attendance runs offline** from your local database afterwards.

## Is it limitation-free?

For a class demo, effectively yes — but here's the honest list so nothing surprises you:

| Thing | Reality |
| --- | --- |
| Always-on intake | ✅ Static host + Supabase don't sleep. Members can submit 24/7. |
| RAM / model limits | ✅ None — the cloud stores photos only; your PC runs the model. |
| Accuracy | ✅ Full `buffalo_l` (same as attendance). |
| Cost | ✅ $0 (Supabase free + free static host). |
| Supabase inactivity pause | ⚠️ Free projects pause after **7 days with zero activity**. Active uploading keeps it awake; if it pauses, click **Restore** in the dashboard (data is kept). |
| Free quotas | ✅ 500 MB DB / 1 GB storage. A class uses a few MB. Photos are wiped after sync. |
| Sync is manual | ⚠️ You run one command when online (not automatic background sync). |
| Photo quality check | ⚠️ Happens at **sync** time, not upload time (the cloud has no model). The guided capture makes bad photos rare; if one fails, sync tells you who should re-submit. |
| Public anon key | ⚠️ It's visible in the page (normal for Supabase). RLS makes it **insert-only** — people can submit but can't read anyone's data. Someone could spam submissions; fine for a class. |

---

## Step 1 — Create the Supabase inbox

1. Create a free project at <https://supabase.com> (no card). Pick a region near you.
2. Open **SQL Editor → New query**, paste the contents of [`supabase_inbox.sql`](supabase_inbox.sql),
   and click **Run**. This creates the `enroll_submissions` table with insert-only security.
3. Go to **Project Settings → API** and note three values:
   - **Project URL** → e.g. `https://abcdefgh.supabase.co`
   - **anon public / publishable** key → goes in the frontend (public-safe with the insert-only policy)
   - **service_role** key → **secret**, stays on your PC only

## Step 2 — Configure the Netlify site

The student app is now React + Vite + shadcn/ui. For a Git-connected Netlify site, open
**Site configuration → Environment variables** and add:

| Key | Value |
| --- | --- |
| `VITE_SUPABASE_URL` | your Project URL, e.g. `https://abcdefgh.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | the **public anon / publishable** key |
| `VITE_ENROLL_EXAM` | `CS101` (or leave unset and pass `--exam` at sync) |

Never put the `service_role` or an `sb_secret_…` key in Netlify browser variables. The public key
is safe here because the inbox policy is insert-only. Trigger a new deploy after changing variables.

## Step 3 — Deploy the built app

**Netlify, Git-connected (recommended):** the root [`netlify.toml`](../netlify.toml) builds from
`frontend/` with `npm ci && npm run build` and publishes `frontend/dist` on Node 22. Push to the
connected branch and let Netlify build. If old dashboard build settings conflict, clear the
overrides so the committed file is used.

**Netlify, drag & drop:** build first, then upload the output — not the source folder. From
`frontend/` in PowerShell:

```powershell
npm ci
npm run build
```

For drag & drop without build-time environment variables, fill in `frontend/public/config.js`
(`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `EXAM`) before building. Then drag **`frontend/dist`** onto
<https://app.netlify.com/drop>. Rebuild and re-upload `dist` after every change.

**Other static hosts:** run the same build and publish `frontend/dist`. Set the same `VITE_*`
variables in the host's build environment.

## Step 4 — Share the link

Send the URL to the group. The details form appears immediately; the camera is requested only
after they continue. Each member enters name + index number (e.g. `PS/CSC/24/0016`) and follows
the live guided capture: look straight, turn left, turn right, while frames are collected
automatically. They'll see **"Capture received — Awaiting organizer sync."** Their submission is
in Supabase; they are not enrolled until you sync on your PC.

## Step 5 — Sync on your PC (when you're online)

From `backend/`, in PowerShell:

```powershell
$env:SUPABASE_URL = "https://abcdefgh.supabase.co"
$env:SUPABASE_SERVICE_KEY = "eyJ...the service_role key..."
uv run --frozen --extra vision python -m app.sync
```

This pulls every pending submission, computes the embeddings with `buffalo_l`, saves them to your
local database, marks each one synced, and **wipes the cloud photos** (privacy). Useful flags:

```powershell
uv run --frozen --extra vision python -m app.sync --dry-run        # just list what's pending
uv run --frozen --extra vision python -m app.sync --keep-photos    # don't wipe cloud photos
uv run --frozen --extra vision python -m app.sync --exam CS101     # fallback exam if not set per-submission
```

`--frozen` uses the committed dependency lock. If your environment already works and you want to
skip package preparation entirely, add `--no-sync`. For package-download timeouts or a fresh
environment, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md); the hybrid does not need the optional
Postgres driver.

> Use your **local** database for the hybrid (the default SQLite). Don't point `DATABASE_URL` at
> Supabase here — the point is that attendance works offline from your PC afterwards.

## Step 6 — Run attendance (offline)

```powershell
uv run --frozen --extra vision python -m app.vision.attend --exam CS101
```

Everyone who synced is now enrolled with full-accuracy embeddings. No internet needed.

---

## Troubleshooting

- **"Set SUPABASE_URL and SUPABASE_SERVICE_KEY"** — you didn't set the env vars in that PowerShell
  window. Set them (Step 5) and re-run. Env vars reset when you close the window.
- **A submission shows `failed`** — run `--dry-run` won't show it (it's no longer pending). Check the
  Supabase table's `error` column, or the sync output. Usually "no face found" → ask that member to
  re-submit with better light, facing the camera.
- **Supabase project paused** — open the dashboard and click **Restore**, then re-run sync.
- **Re-running sync is safe** — already-synced rows are skipped, and re-enrolling a student replaces
  their previous web samples instead of duplicating them.

## Privacy note

Face photos are biometric data. This design keeps them in the cloud only until you sync, then wipes
them. Embeddings live on your PC. Only enroll people who've consented, and delete the Supabase
project (or the table rows) after the module is done.
