"""Errors raised by the SAP client layer."""


class SapClientError(Exception):
    """Base error for anything wrong at the SAP boundary."""


class DocumentNotFoundError(SapClientError):
    """The requested document id does not exist."""


class StagedPostingNotFoundError(SapClientError):
    """The requested staged posting id does not exist."""


class NotEntitledError(SapClientError):
    """The caller is not allowed to perform this operation."""


class NotApprovedError(SapClientError):
    """A write was attempted before a human approved it."""
