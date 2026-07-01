"""Pattern 8: Cash Application / Incoming Payment Matching.

An agent proposes which open invoices an incoming payment clears. A
deterministic guard confirms the match reconciles, a human approves, and only
then does the clearing post to the fake AR ledger. Money is always a Decimal.
"""

from .models import (
    Invoice,
    MatchResult,
    Payment,
    ProposedMatch,
    RemittanceLine,
)
from .ledger import ClearingResult, MockArLedger
from .guard import GuardConfig, GuardVerdict, default_config, check_match
from .proposer import (
    LlmBackedMatcher,
    MatcherError,
    RuleBasedMatcher,
    parse_match,
)
from .flow import FlowResult, run_cash_application

__all__ = [
    "Invoice",
    "Payment",
    "RemittanceLine",
    "ProposedMatch",
    "MatchResult",
    "MockArLedger",
    "ClearingResult",
    "GuardConfig",
    "GuardVerdict",
    "default_config",
    "check_match",
    "RuleBasedMatcher",
    "LlmBackedMatcher",
    "MatcherError",
    "parse_match",
    "FlowResult",
    "run_cash_application",
]
