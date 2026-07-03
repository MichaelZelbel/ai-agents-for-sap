"""The learning loop's memory: what humans corrected, and how often.

Two jobs, both automatic, both on the safe side of the guard:

1. Fold corrections back into the proposal. When a human moves an invoice to a
   different cost center, or rejects it with a reason, we keep that, keyed by the
   vendor. The next invoice from that vendor is proposed with the correction
   already applied and the past reasons shown to the model. The deterministic
   validator still checks every result, so a wrong "learned" value is caught
   exactly like any other. The agent gets better without anyone editing code.

2. Watch the override rate. Every decision, approved-as-is, corrected, or
   rejected, is counted. When the share of drafts the humans had to touch climbs
   past a threshold you set, the store raises a review: it packages the recent
   overrides and their reasons so a person looks because the number moved, not
   because it was a Tuesday.

What it deliberately does NOT do: change the validator's rules, change the model's
weights, or post anything on its own. Those are controls, and controls change
through review, never from live data on their own.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

# A "corrected" or "rejected" decision is an override: the human had to step in.
OVERRIDES = ("corrected", "rejected")


@dataclass(frozen=True)
class Decision:
    """One human decision about one draft, the raw material of the loop."""

    doc_id: str
    vendor: str
    decision: str  # "approved", "corrected", or "rejected"
    reason: str = ""  # the human's free-text note (why they changed or refused it)
    corrected_cost_center: str = ""  # set when the human moved the cost center


@dataclass(frozen=True)
class ReviewDigest:
    """What the store hands a human when the override rate crosses the line."""

    rate: float
    threshold: float
    overrides: int
    total: int
    window: int
    recent: list[dict]  # the recent overrides, with reasons, for the reviewer


class FeedbackStore:
    """An append-only memory of human decisions. Standard library only."""

    def __init__(self, decisions: list[Decision] | None = None) -> None:
        self._decisions: list[Decision] = list(decisions or [])

    # --- write -------------------------------------------------------------- #

    def record(self, decision: Decision) -> None:
        self._decisions.append(decision)

    # --- fold corrections into the next proposal ---------------------------- #

    def cost_center_for(self, vendor: str) -> str | None:
        """The cost center a human last moved this vendor's invoices to, if any.
        The next invoice from this vendor is proposed with it already applied."""
        for d in reversed(self._decisions):
            if d.vendor == vendor and d.corrected_cost_center:
                return d.corrected_cost_center
        return None

    def notes_for(self, vendor: str, limit: int = 3) -> list[str]:
        """Recent human reasons for this vendor, newest first, to show the model."""
        notes = [
            d.reason
            for d in reversed(self._decisions)
            if d.vendor == vendor and d.reason
        ]
        return notes[:limit]

    # --- watch the override rate -------------------------------------------- #

    def override_rate(self, window: int = 50) -> tuple[int, int, float]:
        """Over the last `window` decisions: (overrides, total, rate)."""
        recent = self._decisions[-window:]
        total = len(recent)
        overrides = sum(1 for d in recent if d.decision in OVERRIDES)
        rate = overrides / total if total else 0.0
        return overrides, total, rate

    def review_needed(
        self, *, threshold: float, window: int = 50, min_total: int = 10
    ) -> ReviewDigest | None:
        """A digest when the override rate crosses the threshold, else None. Stays
        quiet below `min_total` decisions so a tiny sample cannot cry wolf."""
        overrides, total, rate = self.override_rate(window)
        if total < min_total or rate <= threshold:
            return None
        recent = [
            asdict(d) for d in self._decisions[-window:] if d.decision in OVERRIDES
        ]
        return ReviewDigest(
            rate=rate,
            threshold=threshold,
            overrides=overrides,
            total=total,
            window=window,
            recent=recent,
        )

    # --- persistence (one JSON object per line) ----------------------------- #

    @classmethod
    def load(cls, path: str | Path) -> "FeedbackStore":
        p = Path(path)
        if not p.exists():
            return cls()
        decisions = [
            Decision(**json.loads(line))
            for line in p.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return cls(decisions)

    def save(self, path: str | Path) -> None:
        lines = [json.dumps(asdict(d)) for d in self._decisions]
        Path(path).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def __len__(self) -> int:
        return len(self._decisions)
