# Troubleshooting (Windows / PowerShell)

## `'uv' is not recognized as the name of a cmdlet...`

PowerShell can't find `uv` on your PATH. This is an environment issue, **not a problem with the
project**. Fix it once and it stays fixed:

**1. Install (or reinstall) uv.** Paste this single line into PowerShell and press Enter:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

(Alternative if you prefer winget: `winget install --id=astral-sh.uv -e`.)

**2. CLOSE PowerShell completely, then open a NEW window.** This step is the one people miss —
the PATH change only applies to windows opened *after* the install. The window you installed from
will still say "not recognized."

**3. Verify and run:**

```powershell
uv --version
cd backend
uv run --extra vision python -m app.sync
```

### If it's *still* not recognized after a new window

uv installs to `%USERPROFILE%\.local\bin`. Confirm it's there, then add that folder to your user
PATH permanently:

```powershell
Test-Path "$env:USERPROFILE\.local\bin\uv.exe"
```

If that returns `True`, run:

```powershell
[Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path","User") + ";$env:USERPROFILE\.local\bin", "User")
```

Then open a **new** PowerShell and try `uv --version` again.

---

## `uv` times out fetching `psycopg` or another package

This happens **before your Python command runs**. It is a package-download/connection problem,
not a face-recognition or Supabase-sync error. Do not reinstall uv when `uv --version` works.

The local hybrid sync uses Supabase's HTTPS API and SQLite; it does **not** need the Postgres
driver. Previously, the committed lock omitted the optional Postgres extra, causing uv to resolve
its metadata again. Pull the updated lock before retrying.

**If your environment already worked before**, run these from `backend/` to skip package syncing:

```powershell
git pull
uv run --frozen --no-sync python -m app.sync --dry-run
```

`--no-sync` uses the existing environment without downloading packages. `--dry-run` only lists
pending submissions; it does not enroll anyone or change cloud data. Once configured, remove
`--dry-run` to sync. If Python reports a missing module, the existing environment is incomplete:
use the one-time setup below instead of `--no-sync`.

For normal subsequent runs, use the committed lock rather than resolving dependencies again:

```powershell
uv run --frozen --extra vision python -m app.sync
```

**Only for a fresh/incomplete environment or a slow connection**, allow more time per request:

```powershell
$env:UV_HTTP_TIMEOUT = "120"
uv sync --frozen --extra vision
```

The first setup still needs a working connection to the package host. If it times out even with
the longer timeout, try another reliable network or phone hotspot. Do not disable TLS certificate
verification or install from an untrusted mirror. The timeout setting lasts for this PowerShell
window only.

## Run project commands from the `backend` folder

`app.sync`, `app.seed`, `app.register`, and `uvicorn` must be run from `backend/`:

```powershell
cd backend
```

If you're at the repo root (`AI-examination-attendance-system>`), `cd backend` first.

## Only paste the commands, not the explanations

Paste just the lines inside the code blocks. Pasting the surrounding prose into PowerShell causes
`ParserError` / "unexpected token" errors.

## `uv run` says the model is downloading / a `FutureWarning` appears

The first run downloads the InsightFace weights (a few hundred MB) — that's normal. A
`FutureWarning` from `SimilarityTransform` is harmless upstream noise; ignore it.

## Netlify enrollment page is stuck on a spinner / shows the old design

The frontend is now a built React + shadcn/ui app. The details form must appear immediately; there
is no startup overlay. If you still see the old spinner:

1. Confirm the latest commit is deployed. Git-connected sites use the root `netlify.toml`
   (`frontend` base, `npm ci && npm run build`, `dist` publish, Node 22).
2. For drag & drop, upload **`frontend/dist` after running `npm ci` and `npm run build`** — never
   the unbuilt `frontend/` source folder.
3. Set `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` (public key only), and `VITE_ENROLL_EXAM` in
   Netlify environment variables, then redeploy. See [HYBRID_SYNC.md](HYBRID_SYNC.md).
4. Hard-refresh the page (or open a private window) to drop the cached old bundle.

If submitting says the enrollment service was not found, the site is in direct-API mode without a
backend. Use the Supabase inbox variables above for Netlify.

## Camera unavailable on the phone

Use the **https://** URL, allow camera access in the browser's site settings, and close other apps
using the camera. The page has a **Try again** button in the camera card; it never blocks the
initial details form while waiting for permission.
