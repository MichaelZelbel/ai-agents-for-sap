"""The scorer: the agent's "predict" step.

This is where the AI reads the close tasks and their signals and scores which
ones are likely to block the critical path. The model only scores. The
mitigation and the plan edit are deterministic and live elsewhere. So a wild
score cannot change the plan on its own.

Two scorers ship here, both behind the same `Scorer` interface:

* `RuleBasedScorer` is deterministic and runs offline with no API key. It is
  the default so `run_agent.py` needs no key.
* `LlmBackedScorer` asks a real model (via OpenRouter) to score the tasks.
  Pass your own `complete` callable to test it offline.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from .models import BlockerPrediction, ClosePlan, CloseTask


class Scorer(Protocol):
    def score(self, plan: ClosePlan) -> list[BlockerPrediction]:
        """Score each task's chance of blocking the close. Scores only."""
        ...


# --- Rule-based scorer -------------------------------------------------------

# Weights for the deterministic score. Kept small and readable on purpose.
_SIGNAL_WEIGHTS = {
    "late_last_period": Decimal("0.30"),
    "queue_backed_up": Decimal("0.25"),
    "owner_overloaded": Decimal("0.20"),
}


def _downstream_count(plan: ClosePlan, task_id: str) -> int:
    """How many tasks sit downstream of this one on the dependency chain.

    A task with more tasks waiting on it blocks more of the close if it slips.
    """
    downstream: set[str] = set()
    frontier = {task_id}
    changed = True
    while changed:
        changed = False
        for task in plan.tasks:
            if task.task_id in downstream:
                continue
            if any(dep in frontier or dep in downstream for dep in task.depends_on):
                downstream.add(task.task_id)
                frontier.add(task.task_id)
                changed = True
    return len(downstream)


def _clamp(value: Decimal) -> Decimal:
    """Keep a score inside 0.00 to 1.00 and round to two places."""
    low, high = Decimal("0.00"), Decimal("1.00")
    return max(low, min(high, value)).quantize(Decimal("0.01"))


class RuleBasedScorer:
    """Scores from the plain signals and the shape of the dependency chain.

    A done task cannot block, so it scores zero. Otherwise the score adds up
    the signal weights plus a small bump for each downstream task. It is
    deterministic, so the same plan always yields the same ranking.
    """

    def score(self, plan: ClosePlan) -> list[BlockerPrediction]:
        predictions = []
        for task in plan.tasks:
            predictions.append(self._score_task(plan, task))
        return predictions

    def _score_task(self, plan: ClosePlan, task: CloseTask) -> BlockerPrediction:
        if task.status == "done":
            return BlockerPrediction(
                task_id=task.task_id,
                score=Decimal("0.00"),
                reasons=("Task is done, it cannot block.",),
            )

        score = Decimal("0.00")
        reasons: list[str] = []

        for signal, weight in _SIGNAL_WEIGHTS.items():
            if getattr(task, signal):
                score += weight
                reasons.append(f"Signal set: {signal.replace('_', ' ')}.")

        downstream = _downstream_count(plan, task.task_id)
        if downstream:
            bump = Decimal("0.05") * downstream
            score += bump
            reasons.append(
                f"{downstream} task(s) wait on this one on the critical path."
            )

        if not reasons:
            reasons.append("No blocking signals.")

        return BlockerPrediction(
            task_id=task.task_id, score=_clamp(score), reasons=tuple(reasons)
        )


# --- Model-backed scorer -----------------------------------------------------

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# A cheap, reliable default. Each scoring pass costs a fraction of a cent.
DEFAULT_MODEL = "openai/gpt-4o-mini"

_SYSTEM = (
    "You are a careful month-end close analyst. You read a set of close tasks "
    "and score which ones are likely to block the critical path. You only "
    "score. A human approves any change to the plan. Reply with JSON only."
)


class ScorerError(RuntimeError):
    """The model returned something we could not turn into scores."""


def _render_examples(examples) -> str:
    """Fold past human decisions for these tasks' owners into the prompt as worked
    examples: what the agent proposed for a task, whether the human applied or
    dismissed the intervention, and why.

    Research caveat, and it is the whole reason this pattern learns cautiously:
    PREDICTION memory transfers poorly. A dismissal on one task, one owner, one
    period is weak evidence about a different task in a different period, far weaker
    than a corrected cost center is for the next invoice from the same vendor. Close
    dynamics shift month to month. So these examples go in as gentle priors only,
    capped and de-duplicated, and the deterministic guard plus the human keep the
    final say. At most the model nudges a score it would otherwise inflate; it can
    never apply anything on its own.
    """
    if not examples:
        return ""
    blocks = []
    for e in examples:
        lines = [f"- Owner {e.entity}, task {e.item_id}."]
        if e.proposed:
            lines.append(f"  The agent proposed: {e.proposed}")
        if e.decision == "rejected":
            lines.append("  A human dismissed the intervention.")
        elif e.decision == "corrected":
            lines.append(f"  A human changed it: {e.correction or e.reason}")
        else:
            lines.append("  A human applied the intervention.")
        if e.reason:
            lines.append(f"  Reason: {e.reason}")
        blocks.append("\n".join(lines))
    return (
        "Past human corrections and dismissals for this owner's tasks. Learn from "
        "them (treat as weak priors, not rules; the risk shifts each period):\n"
        + "\n".join(blocks)
        + "\n\n"
    )


def build_prompt(plan: ClosePlan, examples=None) -> str:
    """The instruction we hand the model. Plain, and it lists every task.

    `examples` are past human dismissals and corrections for the tasks' owners,
    folded in so the model sees what reviewers changed before. Prediction memory
    transfers poorly (see _render_examples), so these are weak priors; the guard
    and the human still decide."""
    lines = [
        "Score each close task from 0.00 to 1.00 for how likely it is to block "
        "the critical path. Higher means more likely to block.\n",
        f"Period: {plan.period}\n",
        "Tasks:",
    ]
    for task in plan.tasks:
        deps = ", ".join(task.depends_on) if task.depends_on else "none"
        signals = [
            name
            for name in ("late_last_period", "queue_backed_up", "owner_overloaded")
            if getattr(task, name)
        ]
        signal_text = ", ".join(signals) if signals else "none"
        lines.append(
            f"- {task.task_id} '{task.name}' owner={task.owner} "
            f"status={task.status} deadline={task.deadline} "
            f"depends_on={deps} signals={signal_text}"
        )
    examples_block = _render_examples(examples)
    if examples_block:
        lines.append("\n" + examples_block.rstrip())
    lines.append(
        '\nReply with ONLY a JSON object of this shape, no prose:\n'
        '{"scores": [{"task_id": "T-02", "score": "0.85"}]}'
    )
    return "\n".join(lines)


def _extract_json(text: str) -> dict[str, Any]:
    """Pull the JSON object out of the model's reply, code fence or not."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ScorerError(f"model did not return JSON: {text[:200]!r}")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ScorerError(f"model returned invalid JSON: {text[:200]!r}") from exc


def parse_scores(raw: str, *, plan: ClosePlan) -> list[BlockerPrediction]:
    """Turn the model's JSON reply into predictions. Structural checks only.

    Every scored task must exist in the plan and carry a numeric score. The
    business meaning of the score is not judged here.
    """
    data = _extract_json(raw)
    known = {task.task_id for task in plan.tasks}
    predictions: list[BlockerPrediction] = []
    for item in data.get("scores", []):
        task_id = str(item.get("task_id", ""))
        if task_id not in known:
            raise ScorerError(f"model scored an unknown task: {item!r}")
        try:
            score = Decimal(str(item["score"]))
        except (KeyError, InvalidOperation) as exc:
            raise ScorerError(f"bad score in model output: {item!r}") from exc
        predictions.append(
            BlockerPrediction(
                task_id=task_id,
                score=_clamp(score),
                reasons=("Scored by the model.",),
            )
        )
    if not predictions:
        raise ScorerError("model scored no tasks")
    return predictions


class LlmBackedScorer:
    """Asks a model to score the close tasks.

    Pass your own `complete` callable to test or to swap providers. By default
    it calls OpenRouter using the OPENROUTER_API_KEY environment variable.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        complete: Callable[[str], str] | None = None,
        store: Any | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self._complete = complete or self._call_openrouter
        # Optional CorrectionMemory. When set, past dismissals and corrections for
        # each task's owner are folded into the prompt as weak priors.
        self._store = store

    def score(self, plan: ClosePlan) -> list[BlockerPrediction]:
        examples = self._gather_examples(plan) if self._store else None
        raw = self._complete(build_prompt(plan, examples=examples))
        return parse_scores(raw, plan=plan)

    def _gather_examples(self, plan: ClosePlan) -> list:
        """Collect the most relevant past overrides for the plan's owners. Prediction
        memory transfers poorly, so we keep it deliberately small: a couple per owner,
        de-duplicated. These are priors for the model; the guard and human still
        decide, and nothing here can move the plan."""
        seen: set = set()
        out: list = []
        for task in plan.tasks:
            for c in self._store.examples_for(task.owner, task.impact, limit=2):
                key = (c.entity, c.proposed, c.correction, c.reason)
                if key in seen:
                    continue
                seen.add(key)
                out.append(c)
        return out

    def _call_openrouter(self, prompt: str) -> str:
        if not self._api_key:
            raise ScorerError("set OPENROUTER_API_KEY to use the model-backed scorer")
        body = json.dumps(
            {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            OPENROUTER_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ScorerError(f"could not reach the model: {exc}") from exc
        return payload["choices"][0]["message"]["content"]
