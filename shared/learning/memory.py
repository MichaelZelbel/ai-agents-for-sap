"""A shared self-learning loop for every pattern: correction memory + override watch.

Every pattern in this repo has the same shape, an AI proposes, a deterministic guard
checks, a human approves or corrects or rejects, and the move is logged. So the loop
that lets the agent learn from those human decisions is the same too, and it lives
here once instead of being rebuilt in each pattern.

Two jobs, both automatic, both on the safe side of the guard:

1. Learn from corrections. Every correction or rejection is kept as a worked example,
   keyed by the recurring entity the pattern turns on (a vendor, a customer, a
   product): what came in, what the agent proposed, what the human changed, and why.
   On a new item we retrieve the most RELEVANT past examples (same entity and similar
   amount, not just the newest) and fold them into the model's prompt. Corrections
   that are exact mappings rather than judgment calls can also be stored as a
   structured field and applied deterministically. The deterministic guard still
   checks every result, so a wrong "learned" value is caught like any other.

2. Watch the override rate. Every decision, approved / corrected / rejected, is
   counted. When the share a human had to touch climbs past a threshold, the memory
   raises a review with the recent overrides, so a person looks because the number
   moved, not because it was a Tuesday.

What it deliberately does NOT do: change a guard's rules, change the model's weights,
or act on its own. Those are controls; they change through review, not from live data.

At scale you would retrieve examples by embedding similarity from a vector store; the
shape is identical, the ranking is just sharper.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

OVERRIDES = ("corrected", "rejected")  # a human had to step in


@dataclass(frozen=True)
class Correction:
    """One human decision about one proposal, the raw material of the loop."""

    entity: str  # the recurring key the pattern turns on: vendor, customer, product
    item_id: str  # the id of the document / case / payment / request
    decision: str  # "approved", "corrected", or "rejected"
    reason: str = ""  # the human's free-text note
    context: str = ""  # a short summary of what came in (the invoice, the request...)
    proposed: str = ""  # a short summary of what the agent proposed
    correction: str = ""  # what the human changed, e.g. "cost center CC-1000 -> CC-2000"
    amount: str = ""  # optional magnitude, kept apart so we can rank by similarity
    fields: dict = field(default_factory=dict)  # structured corrected values, for
    # deterministic defaults, e.g. {"cost_center": "CC-2000"}


@dataclass(frozen=True)
class ReviewDigest:
    """What the memory hands a human when the override rate crosses the line."""

    rate: float
    threshold: float
    overrides: int
    total: int
    window: int
    recent: list  # the recent overrides, with reasons, for the reviewer


class CorrectionMemory:
    """An append-only memory of human decisions, shared by every pattern.

    Standard library only. A production build swaps the relevance ranking for
    embedding similarity in a vector store; nothing else changes."""

    def __init__(self, corrections: list[Correction] | None = None) -> None:
        self._items: list[Correction] = list(corrections or [])

    # --- write -------------------------------------------------------------- #

    def record(self, correction: Correction) -> None:
        self._items.append(correction)

    # --- learn from corrections --------------------------------------------- #

    def examples_for(
        self, entity: str, amount: object | None = None, limit: int = 4
    ) -> list[Correction]:
        """The most RELEVANT past overrides to show the model as worked examples of
        what a person changed, and why. Relevance, not recency: same entity first
        (the strongest signal), then similar amount, newest as the tie-breaker.
        Near-duplicate corrections are dropped and the list is bounded."""
        scored = []
        for i, c in enumerate(self._items):
            if c.decision in OVERRIDES:
                scored.append((self._relevance(c, entity, amount), i, c))
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        out: list[Correction] = []
        seen: set = set()
        for _score, _i, c in scored:
            key = (c.proposed, c.correction, c.reason)
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
            if len(out) >= limit:
                break
        return out

    def learned_field(self, entity: str, name: str) -> str | None:
        """A learned deterministic default: the value a human last set for `name`
        on this entity (e.g. cost_center for a vendor). Apply it through the
        pattern's own determination and let the guard re-check it. This is for
        exact mappings; fuzzier corrections go through examples_for above."""
        for c in reversed(self._items):
            if c.entity == entity and c.fields.get(name):
                return c.fields[name]
        return None

    @staticmethod
    def _relevance(c: Correction, entity: str, amount: object | None) -> float:
        score = 100.0 if c.entity == entity else 0.0
        if amount is not None and c.amount:
            try:
                a = Decimal(str(amount))
                if a != 0:
                    rel = abs(Decimal(c.amount) - a) / abs(a)  # 0 = identical
                    score += 5.0 * max(0.0, 1.0 - float(rel))
            except (InvalidOperation, ArithmeticError):
                pass
        return score

    # --- watch the override rate -------------------------------------------- #

    def override_rate(self, window: int = 50) -> tuple[int, int, float]:
        recent = self._items[-window:]
        total = len(recent)
        overrides = sum(1 for c in recent if c.decision in OVERRIDES)
        return overrides, total, (overrides / total if total else 0.0)

    def review_needed(
        self, *, threshold: float, window: int = 50, min_total: int = 10
    ) -> ReviewDigest | None:
        overrides, total, rate = self.override_rate(window)
        if total < min_total or rate <= threshold:
            return None
        recent = [asdict(c) for c in self._items[-window:] if c.decision in OVERRIDES]
        return ReviewDigest(rate, threshold, overrides, total, window, recent)

    # --- persistence (one JSON object per line) ----------------------------- #

    @classmethod
    def load(cls, path: str | Path) -> "CorrectionMemory":
        p = Path(path)
        if not p.exists():
            return cls()
        items = [
            Correction(**json.loads(line))
            for line in p.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return cls(items)

    def save(self, path: str | Path) -> None:
        lines = [json.dumps(asdict(c)) for c in self._items]
        Path(path).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def __len__(self) -> int:
        return len(self._items)
