"""The deterministic guard: fixed rules, no AI.

This is the leash. The AI may draft any narrative it likes, but where the
request routes is decided here, in plain code you can read, test, and trust.
The model never gets a vote.

The guard checks three things, straight from the policy:

1. Required documentation is present. Software and services need a contract.
2. The amount against the manager spend threshold.
3. Segregation of duties: the requester must not be the named approver.

It returns flags and a route. The route is one of:

* "auto_review"          -- nothing binding tripped; a manager reviews it.
* "escalation"           -- over the threshold or a policy deviation; escalate.
* "blocked_missing_docs" -- a required document is missing; cannot proceed yet.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Policy, Requisition, Supplier


@dataclass(frozen=True)
class GuardConfig:
    # If True, a segregation-of-duties violation escalates instead of passing.
    enforce_segregation_of_duties: bool = True


def default_guard_config() -> GuardConfig:
    return GuardConfig(enforce_segregation_of_duties=True)


@dataclass(frozen=True)
class GuardResult:
    route: str  # "auto_review", "escalation", or "blocked_missing_docs"
    flags: tuple[str, ...]
    policy_version: str  # the version the guard decided against


def run_guard(
    requisition: Requisition,
    supplier: Supplier,
    policy: Policy,
    *,
    config: GuardConfig,
) -> GuardResult:
    """Check a requisition against the policy. Deterministic. Decides the route."""
    flags: list[str] = []

    # 1. Required documentation. A missing contract is a hard block: we cannot
    # sensibly approve a software or services buy with no contract on file.
    missing_contract = (
        requisition.category in policy.contract_required_categories
        and "contract" not in requisition.attached_documents
    )
    if missing_contract:
        flags.append(
            f"Category '{requisition.category}' requires a contract; none attached."
        )

    # 2. Amount against the spend threshold. Over the manager limit is a
    # deviation from the routine path and must escalate.
    over_threshold = requisition.amount > policy.manager_limit
    if over_threshold:
        flags.append(
            f"Amount {requisition.amount} {requisition.currency} exceeds the "
            f"manager limit of {policy.manager_limit}."
        )

    # 3. Segregation of duties. The requester must not be the approver.
    sod_violation = (
        config.enforce_segregation_of_duties
        and requisition.requester == requisition.approver
    )
    if sod_violation:
        flags.append(
            f"Segregation of duties: requester '{requisition.requester}' is also "
            "the named approver."
        )

    # A supplier off the approved vendor list is a deviation worth escalating.
    off_list = not supplier.approved_vendor
    if off_list:
        flags.append(f"Supplier '{supplier.name}' is not on the approved vendor list.")

    # Route. A missing required document blocks: it cannot proceed as is. Any
    # other deviation escalates. A clean request goes to routine review.
    if missing_contract:
        route = "blocked_missing_docs"
    elif over_threshold or sod_violation or off_list:
        route = "escalation"
    else:
        route = "auto_review"

    return GuardResult(route=route, flags=tuple(flags), policy_version=policy.version)
