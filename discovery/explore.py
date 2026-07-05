"""Explore and analyze a system's landscape register.

    python discovery/explore.py                          # a summary of what is custom
    python discovery/explore.py --ask "three-way match"  # which custom objects touch it
    python discovery/explore.py --ask "..." --llm        # a grounded plain-language answer
    python discovery/explore.py --cleancore              # clean-core level per object (A/B/C/D)
    python discovery/explore.py --scorecard              # fit-to-standard: keep/replace/retire, ranked
    python discovery/explore.py --standard               # what is custom vs the standard it leans on
    python discovery/explore.py --opportunities          # where to build AI agents, mapped to the patterns
    python discovery/explore.py --governance             # clean-core risk (Level C/D) by owner
    python discovery/explore.py --diagram --focus "tax"  # a mermaid dependency graph
    python discovery/explore.py --design "three-way match"   # grounded brief + process + BPMN
    python discovery/explore.py --impact ZTHREEWAY_TOL   # what depends on an object
    python discovery/explore.py --grounding --out system.md   # the grounding brief for Claude Code
    python discovery/explore.py --save register.json     # save the whole landscape (+ landscape.md)
    python discovery/explore.py --from register.json --scorecard   # analyze YOUR saved landscape

Runs offline against the seeded fake system. Point it at your own by saving a
register.json (or implementing AbapRepositorySource, see the README) and passing
--from. --llm needs your OpenRouter key in a .env file, the same one the agents use.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))

from shared.dotenv_loader import load_dotenv  # noqa: E402

from discovery.cleancore import render_cleancore  # noqa: E402
from discovery.diagrams import dependency_mermaid, design_brief  # noqa: E402
from discovery.ingest import ingest_file, merge_processes  # noqa: E402
from discovery.landscape import (  # noqa: E402
    render_custom_vs_standard,
    render_governance,
    render_landscape_md,
)
from discovery.landscape import custom_vs_standard  # noqa: E402
from discovery.opportunity import opportunity_map, render_opportunities  # noqa: E402
from discovery.register import (  # noqa: E402
    build_register,
    fit_to_standard_findings,
    to_grounding,
)
from discovery.scorecard import fit_to_standard_scorecard, render_scorecard  # noqa: E402
from discovery.sources import JsonRepositorySource, MockRepositorySource  # noqa: E402

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"


def openrouter_complete(prompt: str) -> str:
    """One model call, grounded and guarded. Returns the model's plain-text answer,
    or a clear note when there is no key or the call fails."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return "(set OPENROUTER_API_KEY in a .env file to get a grounded answer)"
    body = json.dumps(
        {
            "model": DEFAULT_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "You answer questions about a specific SAP system using ONLY "
                    "the landscape grounding provided. If the grounding does not cover it, say "
                    "so plainly. Do not invent object names.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        return f"(could not reach the model: {exc})"
    return payload["choices"][0]["message"]["content"]


def _load_register(args):
    if args.from_json:
        return build_register(JsonRepositorySource(args.from_json))
    return build_register(MockRepositorySource())


def _emit(text: str, out: str | None) -> None:
    if out:
        Path(out).write_text(text, encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(text)


def main() -> None:
    load_dotenv(HERE)
    parser = argparse.ArgumentParser(description="Explore and analyze a landscape register.")
    parser.add_argument("--from", dest="from_json", default=None, help="load the register from a JSON file")
    parser.add_argument("--save", default=None, help="save the register as JSON (writes landscape.md beside it)")
    parser.add_argument(
        "--ingest", action="append", default=[],
        help="fold a BPMN 2.0 file or a BPML CSV into the register's processes (repeatable)",
    )
    parser.add_argument("--ask", default=None, help="find custom objects mentioning this term")
    parser.add_argument("--llm", action="store_true", help="with --ask, also get a grounded answer")
    parser.add_argument("--cleancore", action="store_true", help="clean-core level (A/B/C/D) per object")
    parser.add_argument("--scorecard", action="store_true", help="fit-to-standard: keep/replace/retire, ranked")
    parser.add_argument("--fit-to-standard", action="store_true", help="the plain fit-to-standard findings")
    parser.add_argument("--standard", action="store_true", help="custom vs the standard objects it leans on")
    parser.add_argument("--opportunities", action="store_true", help="AI-agent opportunity map to the patterns")
    parser.add_argument("--governance", action="store_true", help="clean-core risk (Level C/D) by owner")
    parser.add_argument("--diagram", action="store_true", help="a mermaid dependency graph")
    parser.add_argument("--design", default=None, help="a grounded design brief + process + BPMN for a job")
    parser.add_argument("--impact", default=None, help="what depends on an object, and what it depends on")
    parser.add_argument("--grounding", action="store_true", help="print the grounding brief")
    parser.add_argument("--landscape", action="store_true", help="print the readable landscape brief")
    parser.add_argument("--focus", default="", help="narrow --grounding or --diagram to one job")
    parser.add_argument("--out", default=None, help="write the output to a file")
    args = parser.parse_args()

    register = _load_register(args)

    for path in args.ingest:
        incoming = ingest_file(path)
        register = merge_processes(register, incoming)
        print(f"ingested {len(incoming)} process(es) from {path}")

    if args.save:
        Path(args.save).write_text(register.to_json(), encoding="utf-8")
        md = Path(args.save).with_suffix(".md") if Path(args.save).suffix == ".json" else Path("landscape.md")
        md.write_text(render_landscape_md(register), encoding="utf-8")
        print(f"wrote {args.save} and {md}")
        return

    if args.ask is not None:
        hits = register.search(args.ask)
        print(f'\nCustom objects in {register.system} that mention "{args.ask}":\n')
        for o in hits:
            print(f"  {o.name:<20} {o.obj_type:<16} {o.description}")
        if not hits:
            print("  (none)")
        if args.llm:
            print("\nGrounded answer:\n")
            grounding = to_grounding(register, focus=args.ask)
            print(openrouter_complete(f"{grounding}\n\nQuestion: {args.ask}"))
        return

    if args.cleancore:
        print(render_cleancore(register)); return
    if args.scorecard:
        print(render_scorecard(fit_to_standard_scorecard(register))); return
    if args.standard:
        print(render_custom_vs_standard(custom_vs_standard(register))); return
    if args.opportunities:
        print(render_opportunities(opportunity_map(register))); return
    if args.governance:
        print(render_governance(register)); return
    if args.diagram:
        _emit(dependency_mermaid(register, focus=args.focus), args.out); return
    if args.landscape:
        _emit(render_landscape_md(register), args.out); return

    if args.design is not None:
        brief = design_brief(register, args.design)
        if args.out:
            Path(args.out).write_text(brief.to_markdown(), encoding="utf-8")
            bpmn_path = Path(args.out).with_suffix(".bpmn")
            bpmn_path.write_text(brief.bpmn, encoding="utf-8")
            print(f"wrote {args.out} and {bpmn_path}")
        else:
            print(brief.to_markdown())
            print("\n--- BPMN 2.0 (import into Signavio / SAP Build) ---\n")
            print(brief.bpmn)
        return

    if args.impact is not None:
        obj = register.by_name(args.impact)
        print(f"\nImpact of {args.impact}:\n")
        if obj is None:
            print(f"  {args.impact} is not in the register.")
            return
        dependents = register.dependents_of(args.impact)
        print("  Depends on: " + (", ".join(obj.depends_on) or "nothing"))
        print("  Depended on by: " + (", ".join(o.name for o in dependents) or "nothing"))
        return

    if args.fit_to_standard:
        print(f"\nFit-to-standard findings for {register.system}:\n")
        for finding in fit_to_standard_findings(register):
            print(f"  - {finding}")
        return

    if args.grounding:
        _emit(to_grounding(register, focus=args.focus), args.out); return

    # default: a summary
    print(f"\n{register.system}")
    if register.profile.modules_in_use:
        print(f"modules in use: {', '.join(register.profile.modules_in_use)}")
    print(f"{len(register.objects)} custom objects:")
    for obj_type, n in sorted(register.counts().items()):
        print(f"  {n:>3}  {obj_type}")
    print()
    for o in register.objects:
        use = f"{o.monthly_uses}/mo" if o.monthly_uses is not None else "usage n/a"
        level = f"L{o.clean_core_level}" if o.clean_core_level else "  "
        print(f"  {o.name:<20} {o.obj_type:<16} {level:<4} {use:>10}  {o.description}")


if __name__ == "__main__":
    main()
