"""The learning loop's memory: what humans corrected, and how often.

Two jobs, both automatic, both on the safe side of the guard:

1. Fold corrections back into the proposal. Every correction or rejection, on any
   field, is kept as a worked example: the invoice, what the agent proposed, what
   the human changed, and why. On a new invoice we retrieve the most RELEVANT of
   those examples (same vendor and similar amount, not just the newest) and show
   them to the model. One field, the cost center, we can also apply deterministically
   so the loop works even offline with no model. The deterministic validator still
   checks every result, so a wrong "learned" value is caught exactly like any other.
   The agent gets better without anyone editing code.

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
from decimal import Decimal, InvalidOperation
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
    # The lines that make a correction a teachable example for any field:
    invoice: str = ""  # what was on the invoice (net, tax, gross)
    proposed: str = ""  # what the agent proposed (the whole posting)
    correction: str = ""  # what the human changed, e.g. "cost center CC-1000 -> CC-2000"
    gross: str = ""  # the invoice gross, kept apart so we can rank by amount similarity


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

    def examples_for(
        self, vendor: str, gross: object | None = None, limit: int = 4
    ) -> list[Decision]:
        """The most RELEVANT past human overrides to show the model as worked
        examples of what a person changed, and why, whatever the field or reason.

        In-context learning is sensitive to which examples you show, so we pick by
        relevance, not recency: same vendor first (the strongest signal for an
        invoice), then similar amount, newest as the tie-breaker. Near-duplicate
        corrections are dropped, and the list is bounded, so the prompt stays small.
        At scale you would do this with embedding similarity in a vector store; the
        shape is identical, the scoring is just sharper."""
        scored = []
        for i, d in enumerate(self._decisions):
            if d.decision in OVERRIDES:
                scored.append((self._relevance(d, vendor, gross), i, d))
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        out: list[Decision] = []
        seen: set = set()
        for _score, _i, d in scored:
            key = (d.proposed, d.correction, d.reason)
            if key in seen:  # skip a near-identical correction we already have
                continue
            seen.add(key)
            out.append(d)
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _relevance(d: Decision, vendor: str, gross: object | None) -> float:
        """Cheap, dependency-free relevance: vendor match dominates, amount adds a
        little. A production system swaps this for embedding cosine similarity."""
        score = 100.0 if d.vendor == vendor else 0.0
        if gross is not None and d.gross:
            try:
                g = Decimal(str(gross))
                if g != 0:
                    rel = abs(Decimal(d.gross) - g) / abs(g)  # 0 = identical amount
                    score += 5.0 * max(0.0, 1.0 - float(rel))
            except (InvalidOperation, ArithmeticError):
                pass
        return score

    def cost_center_for(self, vendor: str) -> str | None:
        """A shortcut for the one field the offline flow can set on its own: the
        cost center a human last moved this vendor's invoices to. It is applied
        deterministically (and re-checked by the guard), so the loop improves even
        without a model. Everything else is learned through examples_for above."""
        for d in reversed(self._decisions):
            if d.vendor == vendor and d.corrected_cost_center:
                return d.corrected_cost_center
        return None

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
