"""Clean-core classification: how far each custom object is from clean core.

SAP publishes a classification for how an extension touches the system, and how
upgrade-stable that makes it. This module mirrors that public rule offline, so the
model teaches the real vocabulary rather than a made-up one:

  Level A  released/public APIs and released extension points. A stability
           contract. Upgrade-safe. Where you want to be.
  Level B  classic but SAP-nominated: legacy APIs, user-exits, BAdIs, classic
           frameworks. Documented, generally upgrade-stable.
  Level C  partially compliant: reaches into SAP-internal objects. Higher risk.
  Level D  not recommended: core modifications, implicit enhancements, direct
           writes to SAP tables. Severe upgrade risk. Where clean core hurts most.

The real, authoritative rules live in SAP's ATC clean-core checks and the released-
API classification list (github.com/SAP/abap-atc-cr-cv-s4hc). This is a faithful,
deliberately simplified stand-in for teaching, not full ATC parity. A live tenant
gets the real verdict from the ATC clean-core check and the Custom Code Migration
app; here we classify from the object's stated extension mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import CustomObject, ObjectRegister

LEVEL_MEANING = {
    "A": "released or public APIs and released extension points; a stability contract",
    "B": "classic but SAP-nominated: legacy APIs, user-exits, BAdIs, classic frameworks",
    "C": "partially compliant; reaches into SAP-internal objects; higher upgrade risk",
    "D": "core modification, implicit enhancement, or direct table write; not recommended",
}

# The extension mechanism decides the level. This is the teaching rule.
_MECHANISM_LEVEL = {
    "released_api": "A",
    "classic_api": "B",
    "badi": "B",
    "user_exit": "B",
    "implicit_enhancement": "D",
    "modification": "D",
    "direct_table_write": "D",
}

_UPGRADE_SAFE = {"A", "B"}


@dataclass(frozen=True)
class CleanCoreVerdict:
    level: str  # A / B / C / D, or "" if it cannot be determined
    mechanism: str
    upgrade_safe: bool
    reason: str


def classify(obj: CustomObject) -> CleanCoreVerdict:
    """The clean-core verdict for one object.

    Respects an explicitly authored `clean_core_level` when present (a real system,
    or a careful register, states it). Otherwise it derives the level from the
    extension mechanism, and bumps a would-be B up to C when the object reaches into
    SAP-internal objects (`non_released_touched`), which is the classic partial-
    compliance case. A pure data table with no mechanism stays unclassified.
    """
    mechanism = obj.extension_mechanism
    level = obj.clean_core_level

    if not level:
        level = _MECHANISM_LEVEL.get(mechanism, "")
        # Reaching into non-released internal objects is the Level-C signal, unless
        # it is already the worse Level D.
        if obj.non_released_touched and level in ("", "B"):
            level = "C"

    if not level:
        reason = (
            "no extension mechanism recorded, so clean core does not apply here "
            "(for example a plain custom data table)"
        )
        return CleanCoreVerdict(level="", mechanism=mechanism, upgrade_safe=True, reason=reason)

    meaning = LEVEL_MEANING.get(level, "")
    bits = [f"Level {level}: {meaning}"]
    if mechanism:
        bits.append(f"extends via {mechanism.replace('_', ' ')}")
    if obj.non_released_touched:
        bits.append("reaches into " + ", ".join(obj.non_released_touched))
    if level in ("C", "D"):
        bits.append("an upgrade can break it")
    return CleanCoreVerdict(
        level=level,
        mechanism=mechanism,
        upgrade_safe=level in _UPGRADE_SAFE,
        reason="; ".join(bits) + ".",
    )


def classify_register(register: ObjectRegister) -> list[tuple[CustomObject, CleanCoreVerdict]]:
    """Every object with its clean-core verdict, worst level first (D, C, B, A, then
    unclassified), so the risk is at the top."""
    order = {"D": 0, "C": 1, "B": 2, "A": 3, "": 4}
    pairs = [(o, classify(o)) for o in register.objects]
    pairs.sort(key=lambda p: (order.get(p[1].level, 5), p[0].name))
    return pairs


def level_counts(register: ObjectRegister) -> dict[str, int]:
    """How many objects sit at each clean-core level."""
    out: dict[str, int] = {}
    for _, verdict in ((o, classify(o)) for o in register.objects):
        key = verdict.level or "unclassified"
        out[key] = out.get(key, 0) + 1
    return out


def level_d_exposure(register: ObjectRegister) -> list[tuple[CustomObject, CleanCoreVerdict]]:
    """The objects that break clean core the hardest (Level D). These are the
    upgrade risks a governance review cares about first."""
    return [(o, v) for o, v in classify_register(register) if v.level == "D"]


def render_cleancore(register: ObjectRegister) -> str:
    """A plain report: the level counts, then each object with its verdict."""
    lines = [f"Clean-core classification for {register.system}", ""]
    counts = level_counts(register)
    for level in ("A", "B", "C", "D", "unclassified"):
        if level in counts:
            lines.append(f"  Level {level}: {counts[level]}")
    lines.append("")
    for obj, verdict in classify_register(register):
        tag = f"Level {verdict.level}" if verdict.level else "n/a"
        lines.append(f"  {obj.name:<20} {tag:<8} {verdict.reason}")
    lines.append("")
    lines.append(
        "This mirrors SAP's public clean-core classification for teaching. Confirm "
        "the real verdict with the ATC clean-core check and the Custom Code Migration app."
    )
    return "\n".join(lines).rstrip() + "\n"
