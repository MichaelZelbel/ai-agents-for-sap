"""The fit-to-standard scorecard: for each custom object, what to do about it, and
how hard that is, ranked so the most actionable items sit at the top.

This is the analysis Nova Intelligence and the SAP Custom Code Migration app do at
their heart: separate the custom you should keep from the custom you should replace
with standard, re-platform onto a released API, or retire outright. Every finding
prints the real numbers behind it, so nothing is an opaque score. It ranks ease and
risk, not correctness; whether standard truly replaces a custom object is a call for
someone who knows both. The register raises the question honestly; a human answers it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .cleancore import classify
from .models import CustomObject, ObjectRegister
from .register import RETIREMENT_THRESHOLD

# Above this many uses a month, an object touches real volume, so any move that
# changes it is more work and more risk. Documented, not magic; the reasons always
# print the real figure.
BUSY_THRESHOLD = 1000

# What to do with a custom object.
#   retire       barely used; question it, then drop it
#   replace      a standard capability may already cover it
#   re_platform  it works but breaks clean core; move it onto a released API
#   keep         clean and differentiating; keep it (rebuild cleanly if needed)
Move = str


@dataclass(frozen=True)
class FitScore:
    obj: CustomObject
    move: Move
    tier: str  # easy / moderate / hard
    dependents: int
    reasons: tuple[str, ...]
    clean_core_level: str


_MOVE_ORDER = {"retire": 0, "replace": 1, "re_platform": 2, "keep": 3}


def _usage_reason(uses: int | None) -> str:
    if uses is None:
        return "usage not measured, so the size of any change is unknown"
    if uses < RETIREMENT_THRESHOLD:
        return f"barely used ({uses}/mo)"
    if uses < BUSY_THRESHOLD:
        return f"modest usage ({uses}/mo)"
    return f"heavily used ({uses}/mo), so a change touches real volume"


def _dependents_reason(deps: int) -> str:
    if deps == 0:
        return "nothing else depends on it, so it can move without breaking callers"
    if deps <= 2:
        return f"{deps} custom object(s) depend on it"
    return f"{deps} custom objects depend on it, so a change ripples"


def fit_score(register: ObjectRegister, obj: CustomObject) -> FitScore:
    deps = len(register.dependents_of(obj.name))
    uses = obj.monthly_uses
    verdict = classify(obj)
    reasons = [_usage_reason(uses), _dependents_reason(deps)]
    if verdict.level:
        reasons.append(f"clean core Level {verdict.level}")

    barely_used = uses is not None and uses < RETIREMENT_THRESHOLD
    if barely_used:
        move = "retire"
        reasons.append("low use makes it a retirement candidate; confirm, then drop it")
        tier = "easy" if deps == 0 else "moderate"
    elif obj.standard_alternative:
        move = "replace"
        target = obj.standard_alternative
        if obj.replacement_type:
            target += f" (via {obj.replacement_type.replace('_', ' ')})"
        reasons.append(f"standard target: {target}")
        tier = "easy" if deps <= 1 and (uses is None or uses < BUSY_THRESHOLD) else (
            "hard" if deps >= 3 or (uses is not None and uses >= BUSY_THRESHOLD) else "moderate"
        )
    elif verdict.level in ("C", "D"):
        move = "re_platform"
        reasons.append("breaks clean core with no standard replacement; move it onto a released API or side by side")
        tier = "hard" if deps >= 2 or (uses is not None and uses >= BUSY_THRESHOLD) else "moderate"
    else:
        move = "keep"
        reasons.append("clean and differentiating; keep it, and rebuild it on released APIs if you touch it")
        tier = "keep"

    # A recorded high remediation effort keeps it out of the "easy" bucket, whatever
    # the usage and dependency signals say.
    if tier == "easy" and obj.remediation_effort == "high":
        tier = "moderate"
        reasons.append("recorded remediation effort is high")

    return FitScore(
        obj=obj,
        move=move,
        tier=tier,
        dependents=deps,
        reasons=tuple(reasons),
        clean_core_level=verdict.level,
    )


def fit_to_standard_scorecard(register: ObjectRegister) -> list[FitScore]:
    """Every object scored and ranked: the retirements and standard replacements
    first (the fit-to-standard wins), then the clean-core re-platforms, then keep."""
    scores = [fit_score(register, o) for o in register.objects]
    scores.sort(key=lambda s: (_MOVE_ORDER.get(s.move, 9), s.dependents, s.obj.name))
    return scores


def decommission_candidates(register: ObjectRegister) -> list[CustomObject]:
    """Objects used so rarely they should be questioned and likely retired before
    you build anything on them (models the unused-code finding a real tool reports
    from 12-13 months of usage data)."""
    return [
        o
        for o in register.objects
        if o.monthly_uses is not None and o.monthly_uses < RETIREMENT_THRESHOLD
    ]


def retention_candidates(register: ObjectRegister) -> list[CustomObject]:
    """The custom worth keeping: genuinely differentiating (high business value, real
    usage, no standard equivalent, and already clean enough)."""
    out = []
    for o in register.objects:
        used = o.monthly_uses is not None and o.monthly_uses >= BUSY_THRESHOLD
        differentiating = o.business_value == "high" or used
        no_standard = not o.standard_alternative
        clean = classify(o).level in ("", "A", "B")
        if differentiating and no_standard and clean:
            out.append(o)
    return out


def render_scorecard(scores: list[FitScore]) -> str:
    lines = ["Fit-to-standard scorecard (most actionable first)", ""]
    for s in scores:
        level = f"L{s.clean_core_level}" if s.clean_core_level else "  "
        lines.append(f"  {s.obj.name:<20} {s.move:<12} {s.tier:<9} {level}")
        for r in s.reasons:
            lines.append(f"        - {r}")
    lines.append("")
    lines.append(
        "This ranks ease and risk, not correctness. Whether standard truly replaces "
        "a custom object is a call for someone who knows both."
    )
    return "\n".join(lines).rstrip() + "\n"
