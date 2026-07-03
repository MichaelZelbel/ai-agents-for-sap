"""Pattern 9: Sales Order Proposal from a Customer Request.

A customer request arrives as free text. The AI extracts products, quantities,
and terms and proposes a draft sales order. A deterministic guard decides if the
draft is in policy. A human sales manager approves before it is released to
fulfillment. Every step is logged.

The public surface mirrors Pattern 1: models, a proposer (deterministic or
LLM-backed), a deterministic guard, a governed client, and a flow that ties
them together.
"""

from __future__ import annotations

from .models import (
    Customer,
    DraftOrder,
    OrderLine,
    Product,
    ReleaseResult,
    RequestedItem,
    StagedOrder,
)
from .data import (
    CustomerMaster,
    ProductCatalog,
    load_customers,
    load_products,
    load_requests,
)
from .proposer import (
    ExtractedRequest,
    LlmBackedProposer,
    Proposer,
    ProposerError,
    RuleBasedProposer,
    build_prompt,
    parse_extraction,
    price_order,
)
from .guard import GuardConfig, GuardResult, default_config, guard_order
from .governed_client import AuditEntry, GovernedSalesClient
from .mock_client import MockSalesClient
from .flow import DEFAULT_APPROVER, FlowResult, HumanDecision, run_pattern9

__all__ = [
    "Customer",
    "Product",
    "RequestedItem",
    "OrderLine",
    "DraftOrder",
    "StagedOrder",
    "ReleaseResult",
    "CustomerMaster",
    "ProductCatalog",
    "load_customers",
    "load_products",
    "load_requests",
    "Proposer",
    "RuleBasedProposer",
    "LlmBackedProposer",
    "ProposerError",
    "ExtractedRequest",
    "build_prompt",
    "parse_extraction",
    "price_order",
    "GuardConfig",
    "GuardResult",
    "default_config",
    "guard_order",
    "GovernedSalesClient",
    "AuditEntry",
    "MockSalesClient",
    "FlowResult",
    "HumanDecision",
    "DEFAULT_APPROVER",
    "run_pattern9",
]
