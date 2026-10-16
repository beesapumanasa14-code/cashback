from decimal import Decimal

import pytest

from tools import calculate_cashback


def test_cashback_under_cap_and_minimum() -> None:
    result = calculate_cashback(600, 10, 100, 500)
    assert result.cashback == Decimal("60.00")
    assert result.calculated_cashback == Decimal("60.00")
    assert result.final_amount == Decimal("540.00")


def test_cashback_is_limited_by_cap() -> None:
    result = calculate_cashback(2000, 10, 100, 500)
    assert result.calculated_cashback == Decimal("200.00")
    assert result.cashback == Decimal("100.00")
    assert result.final_amount == Decimal("1900.00")


def test_minimum_transaction_is_ineligible() -> None:
    result = calculate_cashback(400, 10, 100, 500)
    assert result.eligible is False
    assert result.cashback == Decimal("0.00")


@pytest.mark.parametrize("amount", [-1, "NaN", "Infinity", "not a number"])
def test_invalid_transaction_amount_is_rejected(amount) -> None:
    with pytest.raises(ValueError):
        calculate_cashback(amount, 10, 100, 500)


def test_missing_rate_does_not_invent_cashback() -> None:
    result = calculate_cashback(600, None, 100, 500)
    assert result.cashback is None
    assert "Cashback percentage or fixed cashback amount" in result.missing_information


def test_missing_cap_does_not_invent_a_zero_cap() -> None:
    result = calculate_cashback(2000, 10, None, 500)
    assert result.cashback == Decimal("200.00")


def test_fixed_cashback_is_supported() -> None:
    result = calculate_cashback(600, fixed_cashback_amount=50)
    assert result.cashback == Decimal("50.00")


def test_both_cashback_types_are_rejected() -> None:
    with pytest.raises(ValueError):
        calculate_cashback(600, 10, fixed_cashback_amount=50)
