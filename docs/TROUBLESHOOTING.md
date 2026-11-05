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
