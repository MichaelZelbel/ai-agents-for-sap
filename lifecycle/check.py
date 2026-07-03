"""Rule on a fleet of agents: for each, print where it is in its life and what the
evidence says to do next.

    python lifecycle/check.py            # rule on the whole example fleet
    python lifecycle/check.py --agent invoice-posting

Runs offline. The decision is deterministic: autonomy is earned on evidence, not
granted on a good feeling.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lifecycle.examples import FLEET  # noqa: E402
from lifecycle.gate import evaluate  # noqa: E402
from lifecycle.models import describe  # noqa: E402

_MARK = {"promote": "^ PROMOTE", "hold": "= HOLD", "review": "! REVIEW", "retire": "x RETIRE"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Rule on where each agent is in its life.")
    parser.add_argument("--agent", default=None, help="only this agent")
    args = parser.parse_args()

    fleet = FLEET
    if args.agent:
        fleet = [(m, x) for (m, x) in FLEET if m.name == args.agent]
        if not fleet:
            print(f"no agent named {args.agent!r}")
            return

    for manifest, metrics in fleet:
        decision = evaluate(manifest, metrics)
        print()
        print(f"  {manifest.name}  ({manifest.autonomy}: {describe(manifest.autonomy)})")
        print(
            f"    prompt {manifest.prompt_version}, model {manifest.model}, "
            f"{metrics.weeks_at_level}w at rung, override {metrics.override_rate:.0%}, "
            f"{metrics.monthly_uses}/mo, audit {'clean' if metrics.audit_clean else 'NOT clean'}"
        )
        print(f"    {_MARK.get(decision.verdict, decision.verdict.upper())}"
              + (f" -> {decision.to_level}" if decision.to_level else ""))
        for reason in decision.reasons:
            print(f"      {reason}")
    print()


if __name__ == "__main__":
    main()
