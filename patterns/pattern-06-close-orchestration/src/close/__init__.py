"""Pattern 6: Close Orchestration and Blocker Prediction.

A month-end close is a graph of dependent tasks. The agent scores which tasks
are likely to block the critical path, ranks them by impact, and proposes a
mitigation for each. Nothing changes the plan until a human approves. The
scoring is the only place a model may weigh in; the mitigation and the plan
edit are deterministic.
"""

from .models import (
    CloseTask,
    ClosePlan,
    BlockerPrediction,
    Mitigation,
    StagedIntervention,
    InterventionResult,
)
from .plan import seed_close_plan, apply_intervention
from .scorer import RuleBasedScorer, LlmBackedScorer, ScorerError
from .mitigation import propose_mitigation
from .flow import predict_and_stage, run_intervention

__all__ = [
    "CloseTask",
    "ClosePlan",
    "BlockerPrediction",
    "Mitigation",
    "StagedIntervention",
    "InterventionResult",
    "seed_close_plan",
    "apply_intervention",
    "RuleBasedScorer",
    "LlmBackedScorer",
    "ScorerError",
    "propose_mitigation",
    "predict_and_stage",
    "run_intervention",
]
