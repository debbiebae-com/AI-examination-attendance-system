"""Sync pending web enrollments from a Supabase "inbox" into this machine's database.

Hybrid architecture:
  * The phone web app stores each submission (name, index number, 3 raw photos) in a Supabase
    table. No face model runs in the cloud, so there is no RAM limit and no accuracy loss.
  * When this PC is online, run this command. It downloads pending submissions, computes the
    embeddings locally with the SAME model used for attendance (default buffalo_l), saves them
    to the local database, and marks each submission synced.
  * Attendance then runs fully offline from the local database.

Usage (from backend/), with SUPABASE_URL and SUPABASE_SERVICE_KEY set:
    uv run --frozen --extra vision python -m app.sync                 # process all pending
    uv run --frozen --extra vision python -m app.sync --dry-run       # just list what's pending
    uv run --frozen --extra vision python -m app.sync --keep-photos   # keep cloud photos after sync

The service-role key is secret and stays on this PC. The browser only ever uses the public
anon key, which Row-Level Security restricts to insert-only.
"""

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import ENROLL_DEFAULT_EXAM, SUPABASE_SERVICE_KEY, SUPABASE_URL
from app.db import SessionLocal, engine
from app.models import Base
from app.vision.embedder import FaceEmbedder
from app.vision.web_enroll import decode_image, enroll_from_photos

TABLE = "enroll_submissions"


class SupabaseInbox:
    """Minimal Supabase REST client for the enrollment inbox (service-role key, server side)."""

    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self.key = key

    def _request(self, method: str, path: str, body: dict | None = None) -> list | dict:
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{self.url}{path}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else []
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise RuntimeError(f"Supabase {method} {path} failed ({exc.code}): {detail}") from exc

    def fetch_pending(self, limit: int | None = None) -> list[dict]:
        path = f"/rest/v1/{TABLE}?status=eq.pending&order=created_at.asc&select=*"
        if limit:
            path += f"&limit={limit}"
        return self._request("GET", path)

    def mark_synced(self, submission_id: str, *, clear_photos: bool = True) -> None:
        body: dict = {"status": "synced", "synced_at": datetime.now(timezone.utc).isoformat()}
        if clear_photos:
            body["photos"] = None  # remove biometric photos from the cloud once processed
        self._request("PATCH", f"/rest/v1/{TABLE}?id=eq.{urllib.parse.quote(submission_id)}", body)

    def mark_failed(self, submission_id: str, error: str) -> None:
        self._request(
            "PATCH",
            f"/rest/v1/{TABLE}?id=eq.{urllib.parse.quote(submission_id)}",
            {"status": "failed", "error": error[:1000]},
        )


@dataclass
class SyncReport:
    synced: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    skipped: int = 0

    @property
    def total(self) -> int:
        return len(self.synced) + len(self.failed)


def sync_submissions(
    session: Session,
    embedder: FaceEmbedder,
    inbox: SupabaseInbox,
    *,
    default_exam: str | None = None,
    keep_photos: bool = False,
    limit: int | None = None,
) -> SyncReport:
    """Process every pending submission. Safe to re-run: synced rows are no longer pending, and
    re-enrolling a student replaces their previous web samples rather than duplicating them."""
    report = SyncReport()
    for sub in inbox.fetch_pending(limit):
        label = f"{sub.get('full_name', '?')} ({sub.get('student_no', '?')})"
        photos = []
        decode_problem = None
        for photo in sub.get("photos") or []:
            image = decode_image(photo.get("image", ""))
            if image is None:
                decode_problem = f"the '{photo.get('step', '?')}' photo could not be read"
                break
            photos.append((photo.get("step", "straight"), image))

        if decode_problem or not photos:
            reason = decode_problem or "no photos were submitted"
            inbox.mark_failed(sub["id"], reason)
            report.failed.append((label, reason))
            continue

        result = enroll_from_photos(
            session,
            embedder,
            student_no=sub.get("student_no", ""),
            full_name=sub.get("full_name", ""),
            photos=photos,
            exam_code=sub.get("exam") or default_exam,
        )
        if result.ok:
            inbox.mark_synced(sub["id"], clear_photos=not keep_photos)
            report.synced.append(label)
        else:
            reason = "; ".join(result.problems) or "no usable face"
            inbox.mark_failed(sub["id"], reason)
            report.failed.append((label, reason))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=SUPABASE_URL, help="Supabase project URL (or SUPABASE_URL env)")
    parser.add_argument("--key", default=SUPABASE_SERVICE_KEY, help="service-role key (or SUPABASE_SERVICE_KEY env)")
    parser.add_argument("--exam", default=ENROLL_DEFAULT_EXAM, help="fallback exam to register sync'd students for")
    parser.add_argument("--model", default=os.getenv("ENROLL_MODEL", "buffalo_l"), help="InsightFace model (must match attendance)")
    parser.add_argument("--limit", type=int, default=None, help="process at most this many pending submissions")
    parser.add_argument("--keep-photos", action="store_true", help="keep the cloud photos after syncing (default: wipe them)")
    parser.add_argument("--dry-run", action="store_true", help="list pending submissions without processing")
    args = parser.parse_args()

    if not args.url or not args.key:
        raise SystemExit("Set SUPABASE_URL and SUPABASE_SERVICE_KEY (or pass --url and --key). See docs/HYBRID_SYNC.md.")

    inbox = SupabaseInbox(args.url, args.key)
    pending = inbox.fetch_pending(args.limit)
    if not pending:
        print("Inbox is empty — nothing to sync.")
        return

    print(f"{len(pending)} pending submission(s):")
    for sub in pending:
        print(f"  - {sub.get('full_name', '?')} ({sub.get('student_no', '?')})")
    if args.dry_run:
        print("\nDry run — nothing was processed.")
        return

    print(f"\nLoading InsightFace ({args.model})...")
    from app.vision.embedder import InsightFaceEmbedder

    embedder = InsightFaceEmbedder(liveness=False, model_name=args.model)

    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        report = sync_submissions(
            session, embedder, inbox, default_exam=args.exam, keep_photos=args.keep_photos, limit=args.limit
        )

    print(f"\nDone: {len(report.synced)} synced, {len(report.failed)} failed.")
    for label in report.synced:
        print(f"  ✓ {label}")
    for label, reason in report.failed:
        print(f"  ✗ {label}: {reason}")
    if report.failed:
        print("\nFailed submissions stay in the inbox as 'failed'. Ask those members to re-submit,")
        print("or inspect the reason above. Re-running this command is safe.")


if __name__ == "__main__":
    main()
