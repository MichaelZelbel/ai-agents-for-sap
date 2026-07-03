"""The manifest and metrics that describe where an agent is in its life.

The autonomy ladder is the spine. An agent climbs it one rung at a time, and only
on evidence. It never jumps rungs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The autonomy ladder, lowest freedom first. This is "set the dial by the risk",
# made into named rungs an agent climbs one at a time.
LADDER: tuple[str, ...] = ("shadow", "suggest_only", "draft_first", "bounded_auto")

_DESCRIPTIONS = {
    "shadow": "runs in parallel and proposes, but its output is not used; you compare it to the humans",
    "suggest_only": "drafts and suggests; a human does everything and the agent acts on nothing",
    "draft_first": "stages a draft; a human approves every one before anything is written",
    "bounded_auto": "handles a narrow, low-risk lane on its own; everything else still needs a human",
}


def describe(level: str) -> str:
    return _DESCRIPTIONS.get(level, level)


def next_level(level: str) -> str | None:
    """The next rung up, or None if already at the top."""
    if level not in LADDER:
        return None
    i = LADDER.index(level)
    return LADDER[i + 1] if i + 1 < len(LADDER) else None


@dataclass(frozen=True)
class AgentManifest:
    """The state of one agent's life. The single record you keep next to it, version
    it, and read in every review. The four owners are the ones from the operate
    chapter; the control owner is never the agent owner."""

    name: str
    purpose: str
    autonomy: str  # one of LADDER
    prompt_version: str
    model: str
    owner_process: str = ""
    owner_agent: str = ""
    owner_control: str = ""
    owner_ops: str = ""
    # Set when a standard SAP capability now covers this job (a retirement trigger).
    standard_now_covers: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        if self.autonomy not in LADDER:
            raise ValueError(f"unknown autonomy level {self.autonomy!r}; use one of {LADDER}")


@dataclass(frozen=True)
class AgentMetrics:
    """What the agent's recent life looks like, from the numbers the operate chapter
    already tells you to keep."""

    weeks_at_level: int  # how long it has run at its current rung
    override_rate: float  # fraction of proposals a human rejected (0..1)
    audit_clean: bool  # the tamper-evident log verifies and no control was breached
    exceptions_per_week: int
    monthly_uses: int
