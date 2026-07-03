"""The promotion gate: read an agent's recent life and rule on it, honestly.

The whole point is that autonomy is earned on evidence, never granted on a good
feeling. So this is deterministic. Given the manifest and the metrics, it returns one
of four verdicts with reasons: promote (climb one rung), hold (keep gathering
evidence), review (something is off, stop and look), or retire (let it go).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import AgentManifest, AgentMetrics, next_level


@dataclass(frozen=True)
class Thresholds:
    min_weeks_at_level: int = 4
    max_override_to_promote: float = 0.05  # 5 percent
    review_override: float = 0.20  # 20 percent: too wrong to promote, go look
    max_exceptions_per_week: int = 20
    retire_uses_per_month: int = 25  # below this, question whether it should exist
    min_weeks_before_retire: int = 12  # do not retire a young agent for low usage
    # The top rung (acting on its own) is the biggest step. Ask for more.
    auto_min_weeks: int = 8
    auto_max_override: float = 0.02


@dataclass(frozen=True)
class Decision:
    verdict: str  # "promote" | "hold" | "review" | "retire"
    to_level: str  # the rung to move to, for a promote; else ""
    reasons: list[str] = field(default_factory=list)


def evaluate(
    manifest: AgentManifest, metrics: AgentMetrics, *, thresholds: Thresholds = Thresholds()
) -> Decision:
    t = thresholds

    # 1. Retire first: a standard now covers it, or it is established but barely used.
    if manifest.standard_now_covers:
        return Decision(
            "retire",
            "",
            ["A standard SAP capability now covers this job. Retire the custom agent and move to standard."],
        )
    if metrics.monthly_uses < t.retire_uses_per_month and metrics.weeks_at_level >= t.min_weeks_before_retire:
        return Decision(
            "retire",
            "",
            [
                f"Only {metrics.monthly_uses} uses a month after {metrics.weeks_at_level} weeks. "
                "Question whether it should exist before you spend more on it."
            ],
        )

    # 2. Review: a broken control or a high override rate. Do not promote; go look.
    if not metrics.audit_clean:
        return Decision(
            "review",
            "",
            ["The audit does not verify or a control was breached. Stop and investigate before anything else."],
        )
    if metrics.override_rate >= t.review_override:
        return Decision(
            "review",
            "",
            [
                f"Humans reject {metrics.override_rate:.0%} of proposals. That is not a promotion case, "
                "it is a calibration case. Review the overrides and fix the prompt, the rules, or the data."
            ],
        )

    # 3. Promote: earned the next rung on evidence.
    nxt = next_level(manifest.autonomy)
    if nxt is not None:
        reasons: list[str] = []
        ok = True
        min_weeks = t.auto_min_weeks if nxt == "bounded_auto" else t.min_weeks_at_level
        max_ovr = t.auto_max_override if nxt == "bounded_auto" else t.max_override_to_promote
        if metrics.weeks_at_level < min_weeks:
            ok = False
            reasons.append(f"needs {min_weeks} weeks at this rung, has {metrics.weeks_at_level}")
        if metrics.override_rate > max_ovr:
            ok = False
            reasons.append(f"override rate {metrics.override_rate:.0%} is above {max_ovr:.0%}")
        if metrics.exceptions_per_week > t.max_exceptions_per_week:
            ok = False
            reasons.append(f"{metrics.exceptions_per_week} exceptions a week is too many to widen")
        if ok:
            note = (
                " This rung lets it act on its own in a narrow lane; confirm the lane and the kill switch first."
                if nxt == "bounded_auto"
                else ""
            )
            return Decision(
                "promote",
                nxt,
                [f"Earned {nxt} ({_short(nxt)}): low override, clean audit, enough runtime.{note}"],
            )
        return Decision("hold", "", ["Not yet ready to widen autonomy: " + "; ".join(reasons) + "."])

    # 4. At the top rung and healthy: hold and keep proving it.
    return Decision(
        "hold",
        "",
        ["At the highest autonomy this ladder grants, and holding. Keep watching the numbers."],
    )


def _short(level: str) -> str:
    from .models import describe

    return describe(level)
