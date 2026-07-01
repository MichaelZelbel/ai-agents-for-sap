"""The drafter, the deterministic guard, and the routing flow.

The shape of this pattern is classify and route. For each expense line:

* The AI *drafts* a verdict: is this line compliant, and why. This is a guess.
* A deterministic guard makes the *real* decision by reading the current,
  versioned policy. It checks the receipt, the category, the per diem cap, the
  reporting period, and assigns the correct approver for the amount.
* The line then routes: compliant lines go to fast approval, a failed check
  goes to the manager, a repeat or high value violation escalates to compliance.
* A human approves exceptions. The log records which policy version was applied.

Two drafters ship, both behind the same interface. `RuleBasedDrafter` is
deterministic and runs offline with no API key, so `run_agent.py` needs no key.
`LlmBackedDrafter` asks a real model via OpenRouter, but it too only drafts. A
wrong draft is caught by the guard and never changes the outcome.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from .models import (
    ExpenseLine,
    ExpenseReport,
    LineVerdict,
    Policy,
    RouteDecision,
)

# A repeat offender: this many failed lines in one report escalates to compliance.
REPEAT_VIOLATION_COUNT = 2


# --- Sample data -------------------------------------------------------------


def default_policy() -> Policy:
    """The current policy version for the book's example."""
    return Policy(
        version="2026.06",
        period_start="2026-06-01",
        period_end="2026-06-30",
        allowed_categories=frozenset({"meals", "lodging", "transport", "supplies"}),
        per_diem_caps={
            "meals": Decimal("60.00"),
            "lodging": Decimal("180.00"),
            "transport": Decimal("300.00"),
            "supplies": Decimal("150.00"),
        },
        receipt_required_above=Decimal("25.00"),
        # Read low to high. The first threshold the amount does not exceed wins.
        approver_tiers=(
            (Decimal("100.00"), "team_lead"),
            (Decimal("500.00"), "manager"),
            (Decimal("1000.00"), "director"),
        ),
        high_value_threshold=Decimal("1000.00"),
    )


def sample_reports() -> dict[str, ExpenseReport]:
    """One report with a compliant line, an over per diem line, and a missing
    receipt line. Enough to see every route without a real SAP account."""
    report = ExpenseReport(
        report_id="EXP-2001",
        employee="Dana Miller",
        currency="EUR",
        lines=(
            # Compliant: within cap, receipt matches, in period.
            ExpenseLine(
                line_id="L1",
                category="meals",
                claimed_amount=Decimal("42.00"),
                receipt_total=Decimal("42.00"),
                date="2026-06-12",
            ),
            # Over per diem: lodging cap is 180, claim is 240.
            ExpenseLine(
                line_id="L2",
                category="lodging",
                claimed_amount=Decimal("240.00"),
                receipt_total=Decimal("240.00"),
                date="2026-06-13",
            ),
            # Missing receipt: over the receipt threshold but receipt total is 0.
            ExpenseLine(
                line_id="L3",
                category="transport",
                claimed_amount=Decimal("90.00"),
                receipt_total=Decimal("0.00"),
                date="2026-06-14",
            ),
        ),
    )
    return {report.report_id: report}


# --- The drafter interface and the offline drafter ---------------------------


class Drafter(Protocol):
    def draft(self, line: ExpenseLine, *, policy: Policy) -> LineVerdict:
        """Draft a compliance verdict for one line. Drafts only; decides nothing."""
        ...


class RuleBasedDrafter:
    """A deterministic stand in for the model. Runs offline with no API key.

    It mirrors the guard's spirit so the draft is usually right, which makes the
    demo readable. The guard still owns the real decision.
    """

    def draft(self, line: ExpenseLine, *, policy: Policy) -> LineVerdict:
        reasons: list[str] = []
        cap = policy.per_diem_caps.get(line.category)
        if line.category not in policy.allowed_categories:
            reasons.append(f"category {line.category!r} looks disallowed")
        if cap is not None and line.claimed_amount > cap:
            reasons.append(f"claim {line.claimed_amount} looks above the {cap} cap")
        if (
            line.claimed_amount >= policy.receipt_required_above
            and line.receipt_total <= 0
        ):
            reasons.append("a receipt seems to be missing")
        if line.receipt_total != line.claimed_amount:
            reasons.append("receipt total does not seem to match the claim")
        compliant = not reasons
        if compliant:
            reasons.append("within cap, receipt matches, category allowed")
        return LineVerdict(
            line_id=line.line_id,
            drafted_compliant=compliant,
            reasons=tuple(reasons),
        )


# --- The deterministic guard: the real decision ------------------------------


def approver_for(amount: Decimal, policy: Policy) -> str:
    """The correct approver for an amount, from the policy tiers.

    Tiers are read low to high. The first threshold the amount does not exceed
    wins. Anything above every tier needs compliance sign off.
    """
    for threshold, approver in policy.approver_tiers:
        if amount <= threshold:
            return approver
    return "compliance"


def guard_line(line: ExpenseLine, *, policy: Policy) -> tuple[bool, tuple[str, ...]]:
    """The deterministic guard for one line. Reads the current policy only.

    Returns whether the line is compliant and the list of failed checks. No AI,
    no float. This is the leash: the draft may say anything, the guard decides.
    """
    failed: list[str] = []

    # 1. The receipt total must equal the claimed amount.
    if line.receipt_total != line.claimed_amount:
        failed.append(
            f"receipt {line.receipt_total} does not equal claim {line.claimed_amount}"
        )

    # 2. A receipt is required at or above the policy threshold.
    if line.claimed_amount >= policy.receipt_required_above and line.receipt_total <= 0:
        failed.append(
            f"receipt required at or above {policy.receipt_required_above}, none given"
        )

    # 3. The category must be allowed by the current policy.
    if line.category not in policy.allowed_categories:
        failed.append(f"category {line.category!r} is not allowed")

    # 4. The per diem or category limit must be respected.
    cap = policy.per_diem_caps.get(line.category)
    if cap is not None and line.claimed_amount > cap:
        failed.append(f"claim {line.claimed_amount} exceeds the {cap} cap")

    # 5. The date must fall inside the reporting period.
    if not (policy.period_start <= line.date <= policy.period_end):
        failed.append(
            f"date {line.date} is outside the period "
            f"{policy.period_start}..{policy.period_end}"
        )

    return (not failed, tuple(failed))


def route_line(
    line: ExpenseLine,
    *,
    policy: Policy,
    prior_failures: int = 0,
    verdict: LineVerdict | None = None,
) -> RouteDecision:
    """Guard one line, then decide where it routes.

    Compliant lines go to fast approval. A failed check routes to the manager.
    A repeat violation (this report already failed enough lines) or a high value
    line escalates to compliance. The policy version travels into the decision.
    """
    compliant, failed = guard_line(line, policy=policy)
    approver = approver_for(line.claimed_amount, policy)

    if compliant:
        route = "fast_approval"
    elif (
        prior_failures + 1 >= REPEAT_VIOLATION_COUNT
        or line.claimed_amount >= policy.high_value_threshold
    ):
        route = "compliance"
    else:
        route = "manager"

    return RouteDecision(
        line_id=line.line_id,
        compliant=compliant,
        route=route,
        approver=approver,
        policy_version=policy.version,
        failed_checks=failed,
        drafted_compliant=None if verdict is None else verdict.drafted_compliant,
    )


# --- The flow: draft, guard, route, log --------------------------------------


@dataclass(frozen=True)
class AuditResult:
    """The outcome of auditing a whole report."""

    report_id: str
    policy_version: str
    decisions: tuple[RouteDecision, ...]
    log: tuple[str, ...]


def audit_report(report: ExpenseReport, *, policy: Policy, drafter: Drafter) -> AuditResult:
    """Audit every line of a report: draft, guard, route, and log.

    The AI drafts each line. The deterministic guard makes the real decision
    against the current policy. Failures accumulate so a repeat offender
    escalates to compliance. Every line's policy version is written to the log.
    """
    decisions: list[RouteDecision] = []
    log: list[str] = []
    prior_failures = 0

    for line in report.lines:
        verdict = drafter.draft(line, policy=policy)
        decision = route_line(
            line,
            policy=policy,
            prior_failures=prior_failures,
            verdict=verdict,
        )
        if not decision.compliant:
            prior_failures += 1

        agreement = "agrees" if verdict.drafted_compliant == decision.compliant else "OVERRIDDEN"
        log.append(
            f"{line.line_id}: policy {decision.policy_version} -> "
            f"{'compliant' if decision.compliant else 'violation'} "
            f"-> route {decision.route} (approver {decision.approver}); "
            f"AI draft {agreement}"
        )
        decisions.append(decision)

    return AuditResult(
        report_id=report.report_id,
        policy_version=policy.version,
        decisions=tuple(decisions),
        log=tuple(log),
    )


# --- Model-backed drafter ----------------------------------------------------

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# A cheap, reliable default. Each draft costs a fraction of a cent. Never
# required: the offline RuleBasedDrafter is the default everywhere.
DEFAULT_MODEL = "openai/gpt-4o-mini"

_SYSTEM = (
    "You are a careful travel and expense auditor. You read one expense line and "
    "the current policy, and you draft whether the line is compliant and why. You "
    "only draft. A deterministic guard makes the real decision and a human approves "
    "exceptions. Reply with JSON only."
)


class DrafterError(RuntimeError):
    """The model returned something we could not turn into a verdict."""


def build_prompt(line: ExpenseLine, policy: Policy) -> str:
    """The instruction handed to the model. Plain, and it shows the policy."""
    cap = policy.per_diem_caps.get(line.category, "no cap for this category")
    return (
        "Draft a compliance verdict for this expense line.\n\n"
        "Line:\n"
        f"- id: {line.line_id}\n"
        f"- category: {line.category}\n"
        f"- claimed amount: {line.claimed_amount}\n"
        f"- receipt total: {line.receipt_total}\n"
        f"- date: {line.date}\n\n"
        f"Policy version {policy.version}:\n"
        f"- reporting period: {policy.period_start} to {policy.period_end}\n"
        f"- allowed categories: {', '.join(sorted(policy.allowed_categories))}\n"
        f"- cap for this category: {cap}\n"
        f"- receipt required at or above: {policy.receipt_required_above}\n\n"
        "A line is compliant only if the receipt total equals the claim, the "
        "category is allowed, the amount is within the cap, a receipt is present "
        "when required, and the date is inside the period.\n\n"
        "Reply with ONLY a JSON object of this shape, no prose:\n"
        '{"compliant": true, "reasons": ["within cap", "receipt matches"]}'
    )


def _extract_json(text: str) -> dict[str, Any]:
    """Pull the JSON object out of the model's reply, code fence or not."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise DrafterError(f"model did not return JSON: {text[:200]!r}")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise DrafterError(f"model returned invalid JSON: {text[:200]!r}") from exc


def parse_verdict(raw: str, *, line: ExpenseLine) -> LineVerdict:
    """Turn the model's JSON reply into a LineVerdict. Structural checks only;
    the business rules are the guard's job."""
    data = _extract_json(raw)
    if "compliant" not in data:
        raise DrafterError(f"model output has no 'compliant' field: {data!r}")
    reasons = data.get("reasons", [])
    if not isinstance(reasons, list):
        raise DrafterError(f"'reasons' must be a list: {reasons!r}")
    return LineVerdict(
        line_id=line.line_id,
        drafted_compliant=bool(data["compliant"]),
        reasons=tuple(str(r) for r in reasons),
    )


class LlmBackedDrafter:
    """Asks a model to draft the verdict for one line.

    Pass your own `complete` callable to test or to swap providers. By default it
    calls OpenRouter using the OPENROUTER_API_KEY environment variable. It is
    never required: the guard and routing work identically with the offline
    drafter, so a missing key only means you skip the model draft.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        complete: Callable[[str], str] | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self._complete = complete or self._call_openrouter

    def draft(self, line: ExpenseLine, *, policy: Policy) -> LineVerdict:
        raw = self._complete(build_prompt(line, policy))
        return parse_verdict(raw, line=line)

    def _call_openrouter(self, prompt: str) -> str:
        if not self._api_key:
            raise DrafterError(
                "set OPENROUTER_API_KEY to use the model-backed drafter"
            )
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
            raise DrafterError(f"could not reach the model: {exc}") from exc
        return payload["choices"][0]["message"]["content"]
