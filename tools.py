"""Deterministic cashback calculations, input validation, and eligibility rules."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


CENT = Decimal("0.01")


def to_decimal(value: Any, field_name: str, *, optional: bool = False) -> Decimal | None:
    """Convert a user-supplied number to Decimal and reject invalid values."""
    if value is None or (isinstance(value, str) and not value.strip()):
        if optional:
            return None
        raise ValueError(f"{field_name} is required.")
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field_name} must be a valid number.") from None
    if not number.is_finite():
        raise ValueError(f"{field_name} must be finite.")
    if number < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    return number


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def parse_offer_date(value: Any) -> date | None:
    """Parse common explicit offer date formats without guessing ambiguous values."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    for date_format in ("%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d %B %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    return None


@dataclass(frozen=True)
class CashbackResult:
    transaction_amount: Decimal
    eligible: bool | None
    calculated_cashback: Decimal | None
    cashback: Decimal | None
    final_amount: Decimal | None
    message: str
    missing_information: tuple[str, ...] = ()


def calculate_cashback(
    transaction_amount: Any,
    cashback_percentage: Any = None,
    maximum_cashback: Any = None,
    minimum_transaction: Any = None,
    fixed_cashback_amount: Any = None,
) -> CashbackResult:
    """Estimate cashback only when the offer contains enough information."""
    amount = to_decimal(transaction_amount, "Transaction amount")
    cap = to_decimal(maximum_cashback, "Maximum cashback", optional=True)
    minimum = to_decimal(minimum_transaction, "Minimum transaction", optional=True)
    percentage = to_decimal(cashback_percentage, "Cashback percentage", optional=True)
    fixed = to_decimal(fixed_cashback_amount, "Fixed cashback amount", optional=True)

    if percentage is not None and fixed is not None:
        raise ValueError("Specify either a cashback percentage or a fixed amount, not both.")

    if minimum is not None and amount < minimum:
        return CashbackResult(
            amount, False, Decimal("0.00"), Decimal("0.00"), _money(amount),
            f"Transaction is below the minimum of Rs. {_money(minimum):.2f}.",
        )

    if percentage is None and fixed is None:
        return CashbackResult(
            amount, None, None, None, None,
            "Cashback cannot be calculated because the offer rate or fixed amount is not specified.",
            ("Cashback percentage or fixed cashback amount",),
        )

    calculated = _money(
        amount * percentage / Decimal("100") if percentage is not None else fixed
    )
    cashback = _money(min(calculated, cap) if cap is not None else calculated)
    return CashbackResult(
        amount, True, calculated, cashback, _money(amount - cashback),
        "Estimated from the supplied offer conditions; provider confirmation is not available.",
    )


def format_cashback_result(result: CashbackResult) -> str:
    """Format a calculation for display."""
    if result.cashback is None:
        return result.message
    if not result.eligible:
        return result.message
    return (
        f"Transaction amount: Rs. {result.transaction_amount:.2f}\n"
        f"Calculated cashback: Rs. {result.calculated_cashback:.2f}\n"
        f"Estimated cashback: Rs. {result.cashback:.2f}\n"
        f"Effective cost after estimated cashback: Rs. {result.final_amount:.2f}\n"
        f"Note: {result.message}"
    )


ELIGIBILITY_STATUSES = (
    "ELIGIBLE_BASED_ON_PROVIDED_RULES",
    "NOT_ELIGIBLE",
    "NEEDS_MORE_INFORMATION",
)


def check_eligibility(conditions: dict[str, Any], user_details: dict[str, Any]) -> dict[str, Any]:
    """Compare provided transaction details with explicit offer restrictions."""
    satisfied: list[str] = []
    failed: list[str] = []
    missing: list[str] = []
    unresolved = conditions.get("required_unknown_conditions", [])
    if isinstance(unresolved, list):
        for item in unresolved:
            condition = item.get("condition") if isinstance(item, dict) else str(item)
            missing.append(f"Mandatory offer condition is unclear: {condition}")

    def compare_list(condition_key: str, detail_key: str, label: str) -> None:
        allowed = conditions.get(condition_key)
        if allowed is None:
            return
        if not isinstance(allowed, list) or not allowed:
            missing.append(f"{label} restrictions could not be interpreted.")
            return
        supplied = user_details.get(detail_key)
        if not supplied:
            missing.append(f"Your {label.lower()} was not provided.")
        elif not any(str(supplied).casefold() == str(item).casefold() for item in allowed):
            failed.append(f"{supplied} is not in the offer's eligible {label.lower()} list.")
        else:
            satisfied.append(f"{label}: {supplied} matches the offer.")

    compare_list("eligible_merchants", "merchant", "merchant")
    compare_list("eligible_banks", "bank", "bank")
    compare_list("eligible_cards", "card", "card")
    compare_list("eligible_payment_methods", "payment_method", "payment method")

    for condition_key, detail_key, label in (
        ("excluded_merchants", "merchant", "Merchant"),
        ("excluded_banks", "bank", "Bank"),
        ("excluded_cards", "card", "Card"),
        ("excluded_payment_methods", "payment_method", "Payment method"),
    ):
        excluded = conditions.get(condition_key)
        supplied = user_details.get(detail_key)
        if isinstance(excluded, list) and excluded:
            if not supplied:
                missing.append(f"Your {label.lower()} was not provided to check exclusions.")
            elif any(str(supplied).casefold() == str(item).casefold() for item in excluded):
                failed.append(f"{supplied} is explicitly excluded.")
            else:
                satisfied.append(f"{label} is not in the listed exclusions.")

    required_boolean_rules = (
        ("new_user_required", "is_new_user", "New-customer requirement"),
        ("coupon_required", "coupon_applied", "Coupon requirement"),
        ("activation_required", "offer_activated", "Offer-activation requirement"),
    )
    for rule_key, detail_key, label in required_boolean_rules:
        required = conditions.get(rule_key)
        if required is True:
            provided = user_details.get(detail_key)
            if provided is None:
                missing.append(f"{label} has not been confirmed.")
            elif provided is not True:
                failed.append(f"{label} is not satisfied.")
            else:
                satisfied.append(f"{label} is satisfied.")
        elif required is False:
            satisfied.append(f"No {label.lower()} is stated.")

    amount_value = user_details.get("transaction_amount")
    if amount_value is not None:
        amount = to_decimal(amount_value, "Transaction amount")
        minimum_value = conditions.get("minimum_transaction")
        if minimum_value is not None:
            minimum = to_decimal(minimum_value, "Minimum transaction")
            if amount < minimum:
                failed.append(f"Transaction is below the minimum of Rs. {_money(minimum):.2f}.")
            else:
                satisfied.append("Transaction meets the minimum amount.")
    else:
        missing.append("Transaction amount was not provided.")

    if failed:
        status = "NOT_ELIGIBLE"
    elif missing:
        status = "NEEDS_MORE_INFORMATION"
    else:
        status = "ELIGIBLE_BASED_ON_PROVIDED_RULES"
    return {
        "status": status,
        "satisfied": satisfied,
        "failed": failed,
        "missing": missing,
        "disclaimer": "Rule-based assessment only; this is not payment-provider confirmation.",
    }
