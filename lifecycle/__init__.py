"""The life of an agent, made concrete.

An agent does not ship once and stay the same. It is born in shadow, earns
suggest-only, then draft-first, then a narrow bounded autonomy, always on evidence.
It is calibrated, watched for drift, re-reviewed when its scope changes, and one day
retired. This package holds the two runnable parts of that story: an `AgentManifest`
(the state of an agent's life, versioned and owned) and a `gate` that reads the
agent's recent metrics and says, honestly, whether it has earned more autonomy, should
hold, needs a review, or should be retired. Everything runs offline.
"""

from .gate import Decision, evaluate
from .models import LADDER, AgentManifest, AgentMetrics, next_level

__all__ = [
    "LADDER",
    "AgentManifest",
    "AgentMetrics",
    "next_level",
    "Decision",
    "evaluate",
]
