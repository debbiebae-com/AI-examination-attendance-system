"""Measure face matching accuracy on real photos (kept on your PC, never committed to Git).

Folder layout under backend/data/probes/ (created automatically on first run):

    reference/<Name>.jpg        one clear photo per enrolled person; the file name is the label
    genuine/<Name>/*.jpg        other photos of that same person (not used for enrollment)
    strangers/*.jpg             photos of people who are NOT enrolled

Run from backend/ after installing the vision extra:

    uv run --extra vision python -m app.vision.evaluate

It reports every probe's outcome at the current threshold, plus a sweep over thresholds
so you can see the trade-off between wrongly accepting strangers and rejecting enrolled people.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.config import BASE_DIR
from app.vision.embedder import DetectedFace, FaceEmbedder
from app.vision.matcher import DEFAULT_MARGIN, DEFAULT_THRESHOLD, FaceMatcher

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp"}
DEFAULT_ROOT = BASE_DIR / "data" / "probes"
SWEEP = [round(t, 2) for t in np.arange(0.20, 0.81, 0.05)]
STRANGER = "stranger"


@dataclass(frozen=True)
class ProbeOutcome:
    label: str  # enrolled person's name, or "stranger"
    photo: str
    verdict: str  # correct, wrong, rejected, false_accept, correct_reject, skipped
    matched: str | None
    score: float
    runner_up: float
    note: str = ""


@dataclass(frozen=True)
class SweepRow:
    threshold: float
    genuine_correct: float  # fraction of genuine probes matched to the right person
    false_accepts: float  # fraction of stranger probes wrongly matched to someone


@dataclass(frozen=True)
class Report:
    gallery_size: int
    reference_problems: list[str]
    outcomes: list[ProbeOutcome]
    sweep: list[SweepRow]


def ensure_layout(root: Path) -> None:
    for sub in ("reference", "genuine", "strangers"):
        (root / sub).mkdir(parents=True, exist_ok=True)


def _images(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)


def _single_embedding(embedder: FaceEmbedder, path: Path) -> tuple[np.ndarray | None, str]:
    try:
        faces: list[DetectedFace] = embedder.detect(path)
    except ValueError:
        return None, "unreadable"
    usable = [f for f in faces if f.embedding is not None]
    if len(usable) == 1:
        return usable[0].embedding, ""
    return None, f"{len(usable)} usable faces found (need exactly 1)"


def collect_probes(root: Path) -> list[tuple[str, Path]]:
    probes: list[tuple[str, Path]] = []
    genuine = root / "genuine"
    if genuine.exists():
        for person_dir in sorted(p for p in genuine.iterdir() if p.is_dir()):
            probes.extend((person_dir.name, path) for path in _images(person_dir))
    probes.extend((STRANGER, path) for path in _images(root / "strangers"))
    return probes


def run_evaluation(
    embedder: FaceEmbedder,
    root: Path,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    margin: float = DEFAULT_MARGIN,
    sweep: list[float] = SWEEP,
) -> Report:
    gallery: list[tuple[str, np.ndarray]] = []
    reference_problems: list[str] = []
    for path in _images(root / "reference"):
        embedding, note = _single_embedding(embedder, path)
        if embedding is None:
            reference_problems.append(f"{path.name}: {note}")
        else:
            gallery.append((path.stem, embedding))

    # Each probe photo is analysed once; only the matching threshold changes between runs.
    analysed = []
    for label, path in collect_probes(root):
        embedding, note = _single_embedding(embedder, path)
        analysed.append((label, path, embedding, note))

    def outcomes_at(t: float) -> list[ProbeOutcome]:
        matcher = FaceMatcher(threshold=t, margin=margin)
        for name, embedding in gallery:
            matcher.enroll(name, embedding)
        results: list[ProbeOutcome] = []
        for label, path, embedding, note in analysed:
            if embedding is None:
                results.append(ProbeOutcome(label, path.name, "skipped", None, 0.0, 0.0, note))
                continue
            result = matcher.match(embedding)
            if label == STRANGER:
                verdict = "false_accept" if result.matched else "correct_reject"
            elif not result.matched:
                verdict = "rejected"
            elif result.student_no == label:
                verdict = "correct"
            else:
                verdict = "wrong"
            results.append(
                ProbeOutcome(label, path.name, verdict, result.student_no, result.score, result.runner_up)
            )
        return results

    def sweep_row(t: float) -> SweepRow:
        outcomes = outcomes_at(t)
        genuine = [o for o in outcomes if o.label != STRANGER and o.verdict != "skipped"]
        strangers = [o for o in outcomes if o.label == STRANGER and o.verdict != "skipped"]
        correct = sum(o.verdict == "correct" for o in genuine) / len(genuine) if genuine else 0.0
        false_accepts = sum(o.verdict == "false_accept" for o in strangers) / len(strangers) if strangers else 0.0
        return SweepRow(threshold=t, genuine_correct=correct, false_accepts=false_accepts)

    return Report(
        gallery_size=len(gallery),
        reference_problems=reference_problems,
        outcomes=outcomes_at(threshold),
        sweep=[sweep_row(t) for t in sweep],
    )


def _print_report(report: Report, threshold: float) -> None:
    print(f"Enrolled reference photos: {report.gallery_size}")
    for problem in report.reference_problems:
        print(f"  reference problem: {problem}")
    if not report.outcomes:
        print("\nNo probe photos found. Add photos under data/probes/genuine/ and data/probes/strangers/.")
        return

    print(f"\n== Probe outcomes at threshold {threshold:.2f} ==")
    for o in report.outcomes:
        matched = o.matched or "-"
        detail = o.note or f"score={o.score:.3f} runner_up={o.runner_up:.3f} matched={matched}"
        print(f"{o.verdict:<15} {o.label:<12} {o.photo:<28} {detail}")

    print("\n== Threshold sweep ==")
    print(f"{'threshold':>9}  {'genuine correct':>15}  {'stranger false accepts':>22}")
    for row in report.sweep:
        print(f"{row.threshold:>9.2f}  {row.genuine_correct:>15.0%}  {row.false_accepts:>22.0%}")

    good = [row for row in report.sweep if row.false_accepts == 0.0]
    if good:
        best = max(good, key=lambda row: (row.genuine_correct, -row.threshold))
        print(
            f"\nLowest-risk threshold with no stranger false accepts: {best.threshold:.2f} "
            f"(genuine correct {best.genuine_correct:.0%}). Treat this as a guide, not a final answer, "
            f"until you have more photos."
        )
    else:
        print("\nNo threshold in the sweep avoids all stranger false accepts. Matching needs better photos or a different approach.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--margin", type=float, default=DEFAULT_MARGIN)
    args = parser.parse_args()

    ensure_layout(args.root)
    if not _images(args.root / "reference"):
        print(f"Created {args.root} with reference/, genuine/ and strangers/.")
        print("Add one clear photo per enrolled person to reference/ (file name = person's name),")
        print("other photos of them to genuine/<name>/, and photos of strangers to strangers/.")
        return

    from app.vision.embedder import InsightFaceEmbedder

    print("Loading InsightFace buffalo_l...")
    report = run_evaluation(
        InsightFaceEmbedder(),
        args.root,
        threshold=args.threshold,
        margin=args.margin,
    )
    _print_report(report, args.threshold)


if __name__ == "__main__":
    main()
