"""Understand your own system before you build an agent for it.

The `discovery` package builds an object register: a structured inventory of the
custom objects in a specific SAP system. That register is what grounds an AI in
YOUR system instead of a generic one, so an agent it builds uses your table names,
your custom fields, and your bespoke logic, not made-up ones.

Everything here runs offline against a seeded fake repository (`MockRepositorySource`).
Point it at a real tenant by implementing `AbapRepositorySource` for your system;
the README explains which repository tables and services to read.
"""

from .models import CustomObject, ObjectRegister
from .register import build_register, fit_to_standard_findings, to_grounding
from .sources import MockRepositorySource, RepositorySource

__all__ = [
    "CustomObject",
    "ObjectRegister",
    "RepositorySource",
    "MockRepositorySource",
    "build_register",
    "to_grounding",
    "fit_to_standard_findings",
]
