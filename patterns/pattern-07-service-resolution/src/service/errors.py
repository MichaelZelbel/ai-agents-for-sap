"""Errors raised at the service resolution boundary."""

from __future__ import annotations


class ServiceError(RuntimeError):
    """Base error for the service source and its governance."""


class CaseNotFoundError(ServiceError):
    def __init__(self, case_id: str) -> None:
        super().__init__(f"case not found: {case_id}")
        self.case_id = case_id


class StagedActionNotFoundError(ServiceError):
    def __init__(self, staged_id: str) -> None:
        super().__init__(f"staged action not found: {staged_id}")
        self.staged_id = staged_id


class NotEntitledError(ServiceError):
    def __init__(self, operation: str) -> None:
        super().__init__(f"agent is not entitled to: {operation}")
        self.operation = operation


class NotConfirmedError(ServiceError):
    def __init__(self, staged_id: str) -> None:
        super().__init__(f"action was not confirmed by a human: {staged_id}")
        self.staged_id = staged_id


class NotAllowedError(ServiceError):
    """The guard did not return allow, so the step may not be staged for a
    one-click confirm."""

    def __init__(self, verdict: str) -> None:
        super().__init__(f"guard verdict does not permit staging: {verdict}")
        self.verdict = verdict
