from dataclasses import dataclass, field


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    reasons: list[str] = field(default_factory=list)


def check_eligibility(*, registered: bool, fees_cleared: bool, suspended: bool) -> EligibilityResult:
    """Decide whether a student may sit an exam.

    Rules (simulated for the demo; replace with the school's real rules later):
      1. The student is registered for the exam.
      2. Fees are cleared.
      3. The student is not suspended or on an academic hold.
    """
    reasons: list[str] = []
    if not registered:
        reasons.append("Not registered for this exam")
    if not fees_cleared:
        reasons.append("Fees not cleared")
    if suspended:
        reasons.append("Suspended or on academic hold")
    return EligibilityResult(eligible=not reasons, reasons=reasons)
