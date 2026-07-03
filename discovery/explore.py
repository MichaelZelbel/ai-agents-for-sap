"""Explore a system's object register.

    python discovery/explore.py                          # a summary of what is custom
    python discovery/explore.py --ask "three-way match"  # which custom objects touch it
    python discovery/explore.py --ask "three-way match" --llm   # a grounded answer
    python discovery/explore.py --grounding --focus "tax" --out system.md
    python discovery/explore.py --fit-to-standard        # where standard may replace custom

Runs offline against the seeded fake system. Point it at a real one by swapping
MockRepositorySource for AbapRepositorySource (see the README). --llm needs your
OpenRouter key in a .env file, the same one the agents use.
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

from discovery.register import (  # noqa: E402
    build_register,
    fit_to_standard_findings,
    to_grounding,
)
from discovery.sources import MockRepositorySource  # noqa: E402

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"


def load_dotenv() -> None:
    for env_file in (REPO / ".env", REPO / "patterns" / "pattern-01-finance-document-to-draft-posting" / ".env"):
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def ask_llm(question: str, grounding: str) -> str:
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
                    "the custom-object grounding provided. If the grounding does not cover it, "
                    "say so plainly. Do not invent object names.",
                },
                {"role": "user", "content": f"{grounding}\n\nQuestion: {question}"},
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


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Explore a system's object register.")
    parser.add_argument("--ask", default=None, help="find custom objects mentioning this term")
    parser.add_argument("--llm", action="store_true", help="with --ask, also get a grounded answer")
    parser.add_argument("--grounding", action="store_true", help="print the grounding brief")
    parser.add_argument("--focus", default="", help="narrow the grounding to one job")
    parser.add_argument("--out", default=None, help="write the grounding to a file")
    parser.add_argument("--fit-to-standard", action="store_true", help="standard-vs-custom findings")
    args = parser.parse_args()

    register = build_register(MockRepositorySource())

    if args.ask is not None:
        hits = register.search(args.ask)
        print(f"\nCustom objects in {register.system} that mention \"{args.ask}\":\n")
        for o in hits:
            print(f"  {o.name:<20} {o.obj_type:<16} {o.description}")
        if not hits:
            print("  (none)")
        if args.llm:
            print("\nGrounded answer:\n")
            print(ask_llm(args.ask, to_grounding(register, focus=args.ask)))
        return

    if args.grounding:
        text = to_grounding(register, focus=args.focus)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"wrote grounding to {args.out}")
        else:
            print(text)
        return

    if args.fit_to_standard:
        print(f"\nFit-to-standard findings for {register.system}:\n")
        for finding in fit_to_standard_findings(register):
            print(f"  - {finding}")
        return

    # default: a summary
    print(f"\n{register.system}")
    print(f"{len(register.objects)} custom objects:")
    for obj_type, n in sorted(register.counts().items()):
        print(f"  {n:>3}  {obj_type}")
    print()
    for o in register.objects:
        use = f"{o.monthly_uses}/mo" if o.monthly_uses is not None else "usage n/a"
        print(f"  {o.name:<20} {o.obj_type:<16} {use:>10}  {o.description}")


if __name__ == "__main__":
    main()
