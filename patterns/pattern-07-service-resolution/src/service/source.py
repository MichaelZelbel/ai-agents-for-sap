"""A small fake source of service data that runs in memory, for free.

It seeds two or three cases with their assets, entitlements, prior incidents, and
parts. It is deliberately simple: just enough to run the pattern end to end with
no external system.

The three seeded cases map to the three guard verdicts:

* CASE-501  in-warranty motor failure, part on hand   -> allow
* CASE-502  repair at a site the plan does not cover   -> needs-approval
* CASE-503  claim on an asset out of warranty          -> deny
"""

from __future__ import annotations

from decimal import Decimal
from itertools import count

from .errors import CaseNotFoundError, StagedActionNotFoundError
from .models import (
    ActionResult,
    Asset,
    CaseContext,
    Entitlement,
    Incident,
    Part,
    ProposedStep,
    ServiceCase,
    StagedAction,
)


def _seed() -> dict[str, CaseContext]:
    contexts = [
        CaseContext(
            case=ServiceCase(
                case_id="CASE-501",
                asset_id="MTR-9001",
                reported_symptom="Motor overheats and trips after ten minutes.",
                site="Hamburg-Plant-A",
            ),
            asset=Asset(
                asset_id="MTR-9001",
                model="NordDrive 3kW",
                site="Hamburg-Plant-A",
                installed_on="2025-11-02",
            ),
            entitlement=Entitlement(
                asset_id="MTR-9001",
                plan="standard-warranty",
                in_warranty=True,
                covered_sites=frozenset({"Hamburg-Plant-A", "Bremen-Plant-B"}),
                approval_limit=Decimal("800.00"),
                expires_on="2027-11-02",
            ),
            incidents=[
                Incident(
                    incident_id="INC-4400",
                    opened_on="2026-03-15",
                    summary="Bearing noise reported, cleared after inspection.",
                ),
            ],
            parts=[
                Part(
                    part_id="PRT-STATOR",
                    name="Stator assembly",
                    in_stock=True,
                    unit_cost=Decimal("420.00"),
                ),
            ],
        ),
        CaseContext(
            case=ServiceCase(
                case_id="CASE-502",
                asset_id="MTR-9002",
                reported_symptom="Gearbox leaks oil under load.",
                site="Leipzig-Plant-C",
            ),
            asset=Asset(
                asset_id="MTR-9002",
                model="NordDrive 5kW",
                site="Leipzig-Plant-C",
                installed_on="2025-06-01",
            ),
            entitlement=Entitlement(
                asset_id="MTR-9002",
                plan="standard-warranty",
                in_warranty=True,
                # Leipzig is not on the covered list. A covered repair here needs
                # a supervisor even though the asset is in warranty.
                covered_sites=frozenset({"Hamburg-Plant-A", "Bremen-Plant-B"}),
                approval_limit=Decimal("800.00"),
                expires_on="2027-06-01",
            ),
            incidents=[],
            parts=[
                Part(
                    part_id="PRT-GEARSEAL",
                    name="Gearbox seal kit",
                    in_stock=True,
                    unit_cost=Decimal("260.00"),
                ),
            ],
        ),
        CaseContext(
            case=ServiceCase(
                case_id="CASE-503",
                asset_id="MTR-9003",
                reported_symptom="Winding shorted, motor will not start.",
                site="Hamburg-Plant-A",
            ),
            asset=Asset(
                asset_id="MTR-9003",
                model="NordDrive 3kW",
                site="Hamburg-Plant-A",
                installed_on="2021-02-10",
            ),
            entitlement=Entitlement(
                asset_id="MTR-9003",
                plan="standard-warranty",
                in_warranty=False,  # warranty already expired
                covered_sites=frozenset({"Hamburg-Plant-A"}),
                approval_limit=Decimal("800.00"),
                expires_on="2024-02-10",
            ),
            incidents=[
                Incident(
                    incident_id="INC-4100",
                    opened_on="2023-08-09",
                    summary="Overload trip, reset on site.",
                ),
            ],
            parts=[
                Part(
                    part_id="PRT-WINDING",
                    name="Winding set",
                    in_stock=False,
                    unit_cost=Decimal("510.00"),
                ),
            ],
        ),
    ]
    return {c.case.case_id: c for c in contexts}


class MockServiceSource:
    """In-memory stand-in for the service systems. Gathers context, stages an
    action, and executes a confirmed one."""

    def __init__(self) -> None:
        self._contexts = _seed()
        self._staged: dict[str, StagedAction] = {}
        self._done: dict[str, ActionResult] = {}
        self._staged_seq = count(1)
        self._action_seq = count(1)

    def gather_context(self, case_id: str) -> CaseContext:
        try:
            return self._contexts[case_id]
        except KeyError:
            raise CaseNotFoundError(case_id) from None

    def stage_action(self, step: ProposedStep) -> StagedAction:
        staged_id = f"STG-{next(self._staged_seq):04d}"
        staged = StagedAction(staged_id=staged_id, step=step)
        self._staged[staged_id] = staged
        return staged

    def execute_action(self, staged_id: str) -> ActionResult:
        staged = self._staged.get(staged_id)
        if staged is None:
            raise StagedActionNotFoundError(staged_id)
        result = ActionResult(
            action_id=f"ACT-{next(self._action_seq):010d}",
            case_id=staged.step.case_id,
        )
        self._done[staged_id] = result
        return result
