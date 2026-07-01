"""Pattern 7: Service Resolution Assist with Entitlement Guardrails.

A service case opens. The agent gathers the asset, the entitlement terms, prior
incidents, and parts availability. The AI proposes the next step. A deterministic
entitlement guard decides allow, deny, or needs-approval. A human confirms
anything that writes. Every decision is logged. Nothing acts without approval.
"""

from .errors import (
    CaseNotFoundError,
    NotAllowedError,
    NotConfirmedError,
    NotEntitledError,
    ServiceError,
    StagedActionNotFoundError,
)
from .flow import FlowResult, run_pattern7
from .governed import AuditEntry, GovernedServiceSource
from .guard import GuardConfig, default_config, evaluate
from .models import (
    ActionResult,
    Asset,
    CaseContext,
    Entitlement,
    GuardDecision,
    Incident,
    Part,
    ProposedStep,
    ServiceCase,
    StagedAction,
    StepKind,
    Verdict,
)
from .proposer import (
    LlmBackedProposer,
    Proposer,
    ProposerError,
    RuleBasedProposer,
    parse_step,
)
from .source import MockServiceSource

__all__ = [
    "run_pattern7",
    "FlowResult",
    "GovernedServiceSource",
    "AuditEntry",
    "MockServiceSource",
    "GuardConfig",
    "default_config",
    "evaluate",
    "Proposer",
    "RuleBasedProposer",
    "LlmBackedProposer",
    "ProposerError",
    "parse_step",
    "Asset",
    "Entitlement",
    "Incident",
    "Part",
    "ServiceCase",
    "CaseContext",
    "ProposedStep",
    "GuardDecision",
    "StagedAction",
    "ActionResult",
    "StepKind",
    "Verdict",
    "ServiceError",
    "CaseNotFoundError",
    "StagedActionNotFoundError",
    "NotEntitledError",
    "NotConfirmedError",
    "NotAllowedError",
]
