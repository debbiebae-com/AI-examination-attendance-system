# Hybrid sync: members upload anytime, your PC embeds when online

This is the recommended setup for your group. It solves the one thing you can't control — *when*
each member is ready to upload — without sacrificing accuracy.

## The idea

```
Member's phone (anytime)                 Your PC (when you're online)
┌──────────────────────┐                ┌────────────────────────────────┐
│ Web app (static host)│                │  python -m app.sync            │
│  name + index + 3 pics│──insert──┐    │   1. pull pending submissions   │
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
   - **anon public** key → goes in the frontend (public-safe)
   - **service_role** key → **secret**, stays on your PC only

## Step 2 — Point the frontend at Supabase

Edit `frontend/config.js`:

```js
window.ENROLL_CONFIG = {
  API_BASE: "",
  EXAM: "CS101",                          // the demo exam (or leave "" and set it at sync)
  SUPABASE_URL: "https://abcdefgh.supabase.co",
  SUPABASE_ANON_KEY: "eyJ...the anon key...",
};
```

Commit and push this change (the anon key is safe to commit — it's insert-only by design).

## Step 3 — Host the frontend (free, always on)

The page is pure static files, so any free static host works. Two easy options:

**Cloudflare Pages (connects to your GitHub repo):**
1. Cloudflare dashboard → **Workers & Pages → Create → Pages → Connect to Git**.
2. Select this repo. Build settings: framework preset **None**, build command *(empty)*,
   build output directory **`frontend`**.
3. Deploy → you get `https://<project>.pages.dev`.

**Netlify (drag & drop):** go to <https://app.netlify.com/drop> and drag the `frontend/` folder
(with `config.js` already filled in). You get an HTTPS URL instantly.

## Step 4 — Share the link

Send the URL to the group. Each member opens it on their phone, enters name + index number, and
captures the 3 photos. They'll see **"Submitted! Queued for sync."** Their data is now safe in
Supabase — your PC can be off.

## Step 5 — Sync on your PC (when you're online)

From `backend/`, in PowerShell:

```powershell
$env:SUPABASE_URL = "https://abcdefgh.supabase.co"
$env:SUPABASE_SERVICE_KEY = "eyJ...the service_role key..."
uv run --extra vision python -m app.sync
```

This pulls every pending submission, computes the embeddings with `buffalo_l`, saves them to your
local database, marks each one synced, and **wipes the cloud photos** (privacy). Useful flags:

```powershell
uv run --extra vision python -m app.sync --dry-run        # just list what's pending
uv run --extra vision python -m app.sync --keep-photos    # don't wipe cloud photos
uv run --extra vision python -m app.sync --exam CS101     # fallback exam if not set per-submission
```

> Use your **local** database for the hybrid (the default SQLite). Don't point `DATABASE_URL` at
> Supabase here — the point is that attendance works offline from your PC afterwards.

## Step 6 — Run attendance (offline)

```powershell
uv run --extra vision python -m app.vision.attend --exam CS101
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
