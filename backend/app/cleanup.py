"""Remove people from the local attendance database, keeping only the ones you name.

Exams are left untouched. For every removed person this also deletes their face embeddings,
exam registrations and attendance records, so the gallery used by live attendance is clean.

Usage (from backend/):

    uv run --frozen python -m app.cleanup --list
    uv run --frozen python -m app.cleanup --keep VOL-002            # dry run
    uv run --frozen python -m app.cleanup --keep VOL-002 --yes      # actually delete

``--keep`` accepts index numbers or full names (case-insensitive). Repeat it or pass several
values to keep more than one person, e.g. ``--keep VOL-002 PS/CSC/24/0016``.

Add ``--purge-inbox`` to also delete Supabase inbox submissions belonging to removed people
(requires SUPABASE_URL + SUPABASE_SERVICE_KEY, and the delete grant from supabase_inbox.sql).
"""

import argparse
from dataclasses import dataclass

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.db import SessionLocal, engine
from app.models import AttendanceRecord, Base, Exam, FaceEmbedding, Registration, Student


@dataclass
class CleanupPlan:
    kept: list[Student]
    removed: list[Student]


@dataclass
class CleanupCounts:
    students: int
    embeddings: int
    registrations: int
    attendance: int


def _normalise(value: str) -> str:
    return value.strip().casefold()


def plan_cleanup(session: Session, keep_identifiers: list[str]) -> CleanupPlan:
    """Resolve the people to keep and raise if any identifier matches nobody."""
    identifiers = [value.strip() for value in keep_identifiers if value.strip()]
    if not identifiers:
        raise ValueError("Pass at least one --keep index number or name.")

    kept: dict[int, Student] = {}
    for identifier in identifiers:
        needle = _normalise(identifier)
        matches = session.scalars(
            select(Student).where(
                or_(func.lower(Student.student_no) == needle, func.lower(Student.full_name) == needle)
            )
        ).all()
        if not matches:
            raise ValueError(f"No person matches '{identifier}'. Run with --list to see the current people.")
        for student in matches:
            kept[student.id] = student

    everyone = session.scalars(select(Student).order_by(Student.student_no)).all()
    removed = [student for student in everyone if student.id not in kept]
    return CleanupPlan(kept=sorted(kept.values(), key=lambda s: s.student_no), removed=removed)


def execute_cleanup(session: Session, plan: CleanupPlan) -> CleanupCounts:
    """Delete the removed people and their dependent rows. Exams are preserved."""
    ids = [student.id for student in plan.removed]
    if not ids:
        return CleanupCounts(0, 0, 0, 0)

    attendance = session.execute(delete(AttendanceRecord).where(AttendanceRecord.student_id.in_(ids))).rowcount or 0
    embeddings = session.execute(delete(FaceEmbedding).where(FaceEmbedding.student_id.in_(ids))).rowcount or 0
    registrations = session.execute(delete(Registration).where(Registration.student_id.in_(ids))).rowcount or 0
    session.execute(delete(Student).where(Student.id.in_(ids)))
    session.commit()
    return CleanupCounts(len(ids), embeddings, registrations, attendance)


def plan_inbox_purge(inbox, keep_student_nos: list[str]) -> list[str]:
    """Ids of inbox rows whose student_no is NOT one of the kept people (case-insensitive)."""
    keep = {value.strip().casefold() for value in keep_student_nos}
    rows = inbox.fetch_all_ids()
    return [row["id"] for row in rows if str(row.get("student_no", "")).strip().casefold() not in keep]


def list_people(session: Session) -> None:
    sample_counts = dict(
        session.execute(
            select(FaceEmbedding.student_id, func.count(FaceEmbedding.id)).group_by(FaceEmbedding.student_id)
        ).all()
    )
    students = session.scalars(select(Student).order_by(Student.student_no)).all()
    if not students:
        print("No people in the local database.")
        return
    print(f"{'Index':<18}{'Name':<28}{'Faces'}")
    print("-" * 56)
    for student in students:
        print(f"{student.student_no:<18}{student.full_name:<28}{sample_counts.get(student.id, 0)}")


def _print_plan(plan: CleanupPlan) -> None:
    print(f"Keeping {len(plan.kept)} person(s):")
    for student in plan.kept:
        print(f"  ✓ {student.full_name} ({student.student_no})")
    print(f"Removing {len(plan.removed)} person(s):")
    for student in plan.removed:
        print(f"  ✗ {student.full_name} ({student.student_no})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--keep", nargs="+", default=[], help="index numbers or full names to keep")
    parser.add_argument("--list", action="store_true", help="list the people currently in the local database")
    parser.add_argument("--yes", action="store_true", help="actually delete (without this the command is a dry run)")
    parser.add_argument("--dry-run", action="store_true", help="force a dry run even if --yes is present")
    parser.add_argument("--purge-inbox", action="store_true", help="also delete Supabase inbox rows for removed people")
    args = parser.parse_args()

    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        if args.list:
            list_people(session)
            return

        try:
            plan = plan_cleanup(session, args.keep)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

        _print_plan(plan)

        inbox = None
        inbox_ids: list[str] = []
        if args.purge_inbox:
            from app.config import SUPABASE_SERVICE_KEY, SUPABASE_URL
            from app.sync import SupabaseInbox

            if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
                raise SystemExit("--purge-inbox needs SUPABASE_URL and SUPABASE_SERVICE_KEY set in this window.")
            inbox = SupabaseInbox(SUPABASE_URL, SUPABASE_SERVICE_KEY)
            inbox_ids = plan_inbox_purge(inbox, [s.student_no for s in plan.kept])
            print(f"Inbox submissions to delete: {len(inbox_ids)}")

        if args.dry_run or not args.yes:
            print("\nDry run — nothing was deleted. Add --yes to apply.")
            return

        counts = execute_cleanup(session, plan)
        exams = session.scalar(select(func.count(Exam.id))) or 0
        print(
            f"\nDone: removed {counts.students} person(s), {counts.embeddings} face sample(s), "
            f"{counts.registrations} registration(s), {counts.attendance} attendance record(s). "
            f"Exams kept: {exams}."
        )
        if inbox is not None:
            inbox.delete_by_ids(inbox_ids)
            print(f"Inbox submissions deleted: {len(inbox_ids)}")


if __name__ == "__main__":
    main()
