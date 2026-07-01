"""Errors raised by the sales client layer."""


class SalesClientError(Exception):
    """Base error for anything wrong at the sales boundary."""


class StagedOrderNotFoundError(SalesClientError):
    """The requested staged order id does not exist."""


class NotEntitledError(SalesClientError):
    """The caller is not allowed to perform this operation."""


class NotApprovedError(SalesClientError):
    """A release was attempted before a human approved it."""
