"""Conservative process-local accounting shared by all turns of one provider."""

from decimal import Decimal
from threading import Lock

from hope_brain.provider import ProviderBudgetExceeded


class SpendBudget:
    def __init__(self, limit: Decimal) -> None:
        if not limit.is_finite() or limit <= 0:
            raise ValueError("invalid spend limit")
        self.limit = limit
        self._lock = Lock()
        self._next = 0
        self._pending: dict[int, Decimal] = {}
        self._accounted = Decimal(0)
        self._unknown = Decimal(0)
        self._overrun = False

    def reserve(self, estimate: Decimal) -> int:
        if not estimate.is_finite() or estimate <= 0:
            raise ValueError("invalid spend estimate")
        with self._lock:
            if self._overrun or self._accounted + sum(self._pending.values()) + estimate > self.limit:
                raise ProviderBudgetExceeded
            self._next += 1
            self._pending[self._next] = estimate
            return self._next

    def settle(self, reservation: int, usage_cost: Decimal | None) -> None:
        if usage_cost is not None and (not usage_cost.is_finite() or usage_cost < 0):
            raise ValueError("invalid usage cost")
        with self._lock:
            reserved = self._pending.pop(reservation)
            # Failed/cancelled requests may still be billed. Keep their entire
            # reservation when complete usage was not received; never refund it.
            self._accounted += reserved if usage_cost is None else usage_cost
            if usage_cost is None:
                self._unknown += reserved
            elif usage_cost > reserved:
                # A bad estimate must stop subsequent spending, even below limit.
                self._overrun = True

    def snapshot(self) -> dict[str, str]:
        with self._lock:
            return {
                "cumulative_limit_usd": str(self.limit),
                "cumulative_accounted_usd": str(self._accounted),
                "cumulative_pending_usd": str(sum(self._pending.values(), Decimal(0))),
                "cumulative_unknown_reserved_usd": str(self._unknown),
                "estimate_overrun": str(self._overrun).lower(),
            }
