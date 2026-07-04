"""Landscape views: what is custom versus the standard it leans on, a governance
summary of the clean-core risk, and the readable landscape brief you hand an AI.

`custom_vs_standard` answers "what is custom, and which standard objects do we lean
on". `governance_summary` rolls up the clean-core exposure (the Level C and D
objects, their owners, and the effort to fix them) the way a governance review
opens. `render_landscape_md` writes the whole landscape as one markdown file that a
human and Claude Code can both read, the durable companion to register.json.
"""

from __future__ import annotations

from dataclasses import dataclass

from .cleancore import classify, classify_register
from .models import CustomObject, ObjectRegister


@dataclass(frozen=True)
class StandardTouchpoint:
    name: str  # a standard SAP object, e.g. LFA1, BKPF
    touched_by: tuple[str, ...]  # custom object names that lean on it


@dataclass(frozen=True)
class CustomVsStandard:
    custom: tuple[CustomObject, ...]
    touchpoints: tuple[StandardTouchpoint, ...]


def custom_vs_standard(register: ObjectRegister) -> CustomVsStandard:
    """The custom objects, and the standard SAP objects they lean on. A standard
    touchpoint is any dependency that is not itself a custom object in the register."""
    custom_names = {o.name.upper() for o in register.objects}
    touched: dict[str, list[str]] = {}
    for o in register.objects:
        for dep in o.depends_on:
            if dep.upper() not in custom_names:
                touched.setdefault(dep, []).append(o.name)
    touchpoints = tuple(
        StandardTouchpoint(name=name, touched_by=tuple(sorted(users)))
        for name, users in sorted(touched.items())
    )
    return CustomVsStandard(custom=register.objects, touchpoints=touchpoints)


def render_custom_vs_standard(view: CustomVsStandard) -> str:
    lines = ["Custom vs standard", "", f"Custom objects ({len(view.custom)}):"]
    for o in view.custom:
        lines.append(f"  {o.name:<20} {o.obj_type}")
    lines.append("")
    lines.append("Standard SAP objects your customizations lean on:")
    for t in view.touchpoints:
        lines.append(f"  {t.name:<12} <- {', '.join(t.touched_by)}")
    return "\n".join(lines).rstrip() + "\n"


@dataclass(frozen=True)
class GovernanceItem:
    name: str
    level: str
    business_owner: str
    remediation_effort: str
    reason: str


def governance_summary(register: ObjectRegister) -> list[GovernanceItem]:
    """The clean-core risk register: the Level C and D objects (the ones an upgrade
    can break), with their owner and effort, worst first."""
    out: list[GovernanceItem] = []
    for obj, verdict in classify_register(register):
        if verdict.level in ("C", "D"):
            out.append(
                GovernanceItem(
                    name=obj.name,
                    level=verdict.level,
                    business_owner=obj.business_owner or "(unowned)",
                    remediation_effort=obj.remediation_effort or "unknown",
                    reason=verdict.reason,
                )
            )
    return out


def render_governance(register: ObjectRegister) -> str:
    items = governance_summary(register)
    lines = [f"Clean-core governance summary for {register.system}", ""]
    if not items:
        lines.append("  No Level C or D exposure recorded. Keep it that way.")
    else:
        lines.append(f"  {len(items)} object(s) an upgrade can break (Level C or D):")
        lines.append("")
        for i in items:
            lines.append(f"  {i.name:<20} Level {i.level}   owner: {i.business_owner}   effort: {i.remediation_effort}")
            lines.append(f"        {i.reason}")
    lines.append("")
    lines.append(
        "Govern these first: name an owner for every Level-D object, cap new Level-D "
        "extensions, and move the worst onto released APIs. A human rules; this raises the question."
    )
    return "\n".join(lines).rstrip() + "\n"


def render_landscape_md(register: ObjectRegister) -> str:
    """The whole landscape as one readable markdown brief, the durable companion to
    register.json that a human and Claude Code both read. Names only what is in the
    register, and tells the AI not to invent."""
    p = register.profile
    lines = [
        f"# {register.system}: landscape brief",
        "",
        "This is your analyzed SAP landscape. When you answer questions or build for "
        "it, use only the objects, processes, and interfaces named here. Do not invent "
        "names; if something you need is not here, say so instead of guessing.",
        "",
        "## Profile",
        "",
    ]
    if p.product:
        lines.append(f"- Product: {p.product}")
    if p.modules_in_use:
        lines.append(f"- Modules in use: {', '.join(p.modules_in_use)}")
    if p.modules_not_used:
        lines.append(f"- Modules not in use: {', '.join(p.modules_not_used)}")
    if p.detail:
        lines.append(f"- {p.detail}")
    lines.append("")

    lines.append("## Custom objects")
    lines.append("")
    for obj, verdict in classify_register(register):
        level = f"clean core Level {verdict.level}" if verdict.level else "clean core n/a"
        use = f"~{obj.monthly_uses}/mo" if obj.monthly_uses is not None else "usage n/a"
        deps = f" Depends on: {', '.join(obj.depends_on)}." if obj.depends_on else ""
        alt = f" Standard alternative: {obj.standard_alternative}" if obj.standard_alternative else ""
        lines.append(
            f"- **{obj.name}** ({obj.obj_type}, package {obj.package}): {obj.description} "
            f"[{level}, {use}, owner {obj.business_owner or 'unknown'}].{deps}{alt}"
        )
    lines.append("")

    if register.processes:
        lines.append("## Business processes")
        lines.append("")
        for pr in register.processes:
            vol = f"~{pr.monthly_volume}/mo" if pr.monthly_volume is not None else "volume n/a"
            objs = f" Objects: {', '.join(pr.objects)}." if pr.objects else ""
            dev = f" Deviation: {pr.deviation_from_standard}." if pr.deviation_from_standard else ""
            lines.append(
                f"- **{pr.name}** ({pr.area}): {vol}, {pr.manual_rework or 'unknown'} manual effort.{dev}{objs}"
            )
        lines.append("")

    if register.interfaces:
        lines.append("## Interfaces")
        lines.append("")
        for it in register.interfaces:
            dep = f" Depends on: {', '.join(it.depends_on)}." if it.depends_on else ""
            lines.append(
                f"- **{it.name}** ({it.itype}, {it.direction}) to {it.external_system}, "
                f"criticality {it.criticality or 'unknown'}.{dep}"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
