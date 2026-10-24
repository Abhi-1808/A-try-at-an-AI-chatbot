"""Budget boundaries, simultaneous reservations and uncertain billing."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest

from hope_brain.provider import ProviderBudgetExceeded
from hope_brain.spend import SpendBudget


def test_exact_boundary_and_usage_reconciliation():
    budget = SpendBudget(Decimal("0.05"))
    first = budget.reserve(Decimal("0.03"))
    second = budget.reserve(Decimal("0.02"))
    with pytest.raises(ProviderBudgetExceeded):
        budget.reserve(Decimal("0.001"))
    budget.settle(first, Decimal("0.01"))
    budget.settle(second, None)
    budget.settle(budget.reserve(Decimal("0.02")), None)
    snapshot = budget.snapshot()
    assert Decimal(snapshot["cumulative_accounted_usd"]) == Decimal("0.05")
    assert Decimal(snapshot["cumulative_unknown_reserved_usd"]) == Decimal("0.04")
    with pytest.raises(ProviderBudgetExceeded):
        budget.reserve(Decimal("0.001"))


def test_estimate_overrun_stops_following_calls():
    budget = SpendBudget(Decimal("0.05"))
    budget.settle(budget.reserve(Decimal("0.001")), Decimal("0.002"))
    with pytest.raises(ProviderBudgetExceeded):
        budget.reserve(Decimal("0.001"))
    assert budget.snapshot()["estimate_overrun"] == "true"


def test_concurrent_reservations_cannot_oversubscribe():
    budget = SpendBudget(Decimal("0.01"))

    def attempt(_):
        try:
            return budget.reserve(Decimal("0.003"))
        except ProviderBudgetExceeded:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        accepted = [value for value in pool.map(attempt, range(30)) if value is not None]
    assert len(accepted) == 3
    assert len(set(accepted)) == 3
    assert Decimal(budget.snapshot()["cumulative_pending_usd"]) == Decimal("0.009")


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity"])
def test_invalid_limits_and_reservations(value):
    with pytest.raises(ValueError):
        SpendBudget(Decimal(value))
    with pytest.raises(ValueError):
        SpendBudget(Decimal("0.05")).reserve(Decimal(value))
