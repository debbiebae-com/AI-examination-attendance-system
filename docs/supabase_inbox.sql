-- ============================================================================
-- Supabase "inbox" for hybrid enrollment
-- Run this once in: Supabase Dashboard -> SQL Editor -> New query -> Run.
-- See docs/HYBRID_SYNC.md for the full walkthrough.
-- ============================================================================

-- The inbox table. Each row is one member's submission (name, index number, 3 photos).
-- Photos are stored as base64 in a JSONB column and are WIPED after the organizer syncs,
-- so biometric data doesn't linger in the cloud.
create table if not exists public.enroll_submissions (
  id          uuid primary key default gen_random_uuid(),
  student_no  text not null,
  full_name   text not null,
  exam        text,
  photos      jsonb,                       -- [{step, image(base64)}]; null after sync
  status      text not null default 'pending',   -- pending | synced | failed
  error       text,
  created_at  timestamptz not null default now(),
  synced_at   timestamptz
);

-- Fast lookup of pending rows for the sync command.
create index if not exists enroll_submissions_status_idx
  on public.enroll_submissions (status, created_at);

-- Lock the table down with Row-Level Security.
alter table public.enroll_submissions enable row level security;

-- The PUBLIC anon key (used by the phone web app) may INSERT a submission but cannot
-- read, update, or delete anyone's data. Members can't see each other's submissions.
grant insert on public.enroll_submissions to anon;
drop policy if exists "anon can submit" on public.enroll_submissions;
create policy "anon can submit" on public.enroll_submissions
  for insert to anon with check (true);

-- The SECRET service_role key (used only by the organizer's PC sync) reads pending rows
-- and marks them synced/failed. service_role bypasses RLS, so it needs grants, not policies.
grant select, update on public.enroll_submissions to service_role;

-- ============================================================================
-- That's it. Now:
--   1. Put your Project URL + anon key in frontend/config.js (SUPABASE_URL / SUPABASE_ANON_KEY).
--   2. Host the frontend/ folder on any free static host (Cloudflare Pages / Netlify).
--   3. On your PC, set SUPABASE_URL + SUPABASE_SERVICE_KEY and run:
--        uv run --extra vision python -m app.sync
-- ============================================================================
