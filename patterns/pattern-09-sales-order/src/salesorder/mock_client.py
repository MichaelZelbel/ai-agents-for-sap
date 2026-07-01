"""A fake sales system that runs in memory, for free, with no SAP account.

It loads the sample master data, lets you stage a draft order, and lets you
release it to fulfillment. It is deliberately simple: just enough to run the
pattern end to end.
"""

from __future__ import annotations

from itertools import count

from .data import (
    CustomerMaster,
    ProductCatalog,
    load_customers,
    load_products,
)
from .errors import StagedOrderNotFoundError
from .models import DraftOrder, ReleaseResult, StagedOrder


class MockSalesClient:
    """In-memory stand-in for the sales side of SAP."""

    def __init__(self) -> None:
        self.customers: CustomerMaster = load_customers()
        self.catalog: ProductCatalog = load_products()
        self._staged: dict[str, StagedOrder] = {}
        self._released: dict[str, ReleaseResult] = {}
        self._staged_seq = count(1)
        self._order_seq = count(1)

    def stage_order(self, order: DraftOrder) -> StagedOrder:
        staged_id = f"SO-STG-{next(self._staged_seq):04d}"
        staged = StagedOrder(staged_id=staged_id, order=order)
        self._staged[staged_id] = staged
        return staged

    def release_order(self, staged_id: str) -> ReleaseResult:
        staged = self._staged.get(staged_id)
        if staged is None:
            raise StagedOrderNotFoundError(staged_id)
        result = ReleaseResult(
            order_id=f"SO-{next(self._order_seq):010d}",
            request_id=staged.order.request_id,
        )
        self._released[staged_id] = result
        return result
