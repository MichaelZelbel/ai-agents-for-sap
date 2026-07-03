"""Build the register, check it against SAP standard, and turn it into grounding.

Three jobs:
- `build_register` reads a source into an `ObjectRegister`.
- `fit_to_standard_findings` flags custom objects a standard SAP capability may
  already cover, and objects barely used enough to retire. Before you build custom,
  or wrap custom in an agent, this asks whether you should be keeping it at all.
- `to_grounding` turns the register into a short markdown brief you hand an AI
  (Claude Code) so what it builds uses your object names, not invented ones.
"""

from __future__ import annotations

from .models import ObjectRegister
from .sources import RepositorySource

# Below this many uses a month, an object is worth questioning, not automating.
RETIREMENT_THRESHOLD = 25


def build_register(source: RepositorySource) -> ObjectRegister:
    return ObjectRegister(system=source.system_name(), objects=tuple(source.objects()))


def fit_to_standard_findings(register: ObjectRegister) -> list[str]:
    """Plain findings: where a standard capability may replace custom, and where a
    custom object is used so rarely it should be questioned before it is automated."""
    findings: list[str] = []
    for o in register.objects:
        if o.standard_alternative:
            findings.append(
                f"{o.name} ({o.obj_type}): {o.standard_alternative} "
                f"Confirm the standard fit before wrapping this in an agent."
            )
        if o.monthly_uses is not None and o.monthly_uses < RETIREMENT_THRESHOLD:
            findings.append(
                f"{o.name} ({o.obj_type}): only {o.monthly_uses} uses a month. "
                f"Question whether it should exist before you build on it."
            )
    return findings


def _line(o) -> str:
    deps = f" Depends on: {', '.join(o.depends_on)}." if o.depends_on else ""
    detail = f" ({o.detail})" if o.detail else ""
    use = f" ~{o.monthly_uses}/mo." if o.monthly_uses is not None else ""
    return f"- **{o.name}** ({o.obj_type}, package {o.package}): {o.description}{detail}{deps}{use}"


def to_grounding(register: ObjectRegister, *, focus: str = "") -> str:
    """A short markdown brief to hand an AI so its build fits this system.

    With `focus` (for example "three-way match"), it narrows to the objects that
    mention it and everything they depend on, so the AI sees exactly the custom
    parts of that job. Without a focus, it lists everything, grouped by type.
    """
    lines: list[str] = [
        f"# {register.system}: custom-object grounding",
        "",
        "This is what is custom in this system. When you build an agent for it, use "
        "these object names and respect these dependencies. Do not invent names; if "
        "something you need is not here, say so instead of guessing.",
        "",
    ]

    objects = register.objects
    if focus:
        hit = list(register.search(focus))
        needed = {o.name.upper() for o in hit}
        for o in hit:
            needed.update(d.upper() for d in o.depends_on)
        objects = tuple(o for o in register.objects if o.name.upper() in needed)
        lines.append(f"## Custom objects relevant to \"{focus}\"")
        lines.append("")
        if not objects:
            lines.append(f"Nothing custom in this system mentions \"{focus}\".")
            lines.append("")

    if objects and not focus:
        for obj_type in sorted({o.obj_type for o in objects}):
            lines.append(f"## {obj_type.replace('_', ' ').title()}s")
            lines.append("")
            lines.extend(_line(o) for o in objects if o.obj_type == obj_type)
            lines.append("")
    elif objects:
        lines.extend(_line(o) for o in objects)
        lines.append("")

    findings = fit_to_standard_findings(register)
    relevant = findings
    if focus:
        names = {o.name for o in objects}
        relevant = [f for f in findings if f.split(" ")[0] in names]
    if relevant:
        lines.append("## Fit-to-standard notes")
        lines.append("")
        lines.extend(f"- {f}" for f in relevant)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
