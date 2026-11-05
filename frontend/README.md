# Student enrollment frontend

React 19 + Vite + TypeScript + Tailwind CSS 4 + [shadcn/ui](https://ui.shadcn.com) (new-york,
neutral). The details form renders immediately; the camera is requested only on the photos step,
and submission loading is inline on the submit button.

## Commands

```bash
npm ci
npm run dev        # http://localhost:5173, API proxied to BACKEND_ORIGIN (default 127.0.0.1:8000)
npm test           # Vitest + Testing Library
npm run typecheck
npm run build      # outputs dist/
npm run preview    # serve the built dist/
```

Node 22.12+ is required. The backend serves the built `dist/` at `/app`; run `npm run build`
before local FastAPI serving. Docker and Netlify build automatically.

## Configuration

Copy `.env.example` to `.env.local` for local builds, or set the same variables in Netlify:

- `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY` — hybrid inbox mode. **Public anon/publishable
  key only**; never a `service_role` or `sb_secret_…` key.
- `VITE_ENROLL_EXAM` — optional exam code attached to submissions.
- `VITE_API_BASE` — direct mode only; leave empty for same-origin/Vite proxy.

`public/config.js` is copied unchanged to `dist/config.js` as an optional runtime override for
older/drag-and-drop deployments. Non-empty `VITE_*` build variables take precedence.

## Deployment

Git-connected Netlify uses the root `netlify.toml` (base `frontend`, build `npm ci && npm run
build`, publish `dist`). For drag & drop, upload **`dist` after building**, not this source folder.
See [../docs/HYBRID_SYNC.md](../docs/HYBRID_SYNC.md) and [../docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md).

shadcn/ui component sources and license are in `src/components/ui/` (`SOURCE.md`, `LICENSE.md`).
