from tools import check_eligibility


def test_unknown_mandatory_merchant_condition_needs_more_information() -> None:
    result = check_eligibility(
        {
            "eligible_merchants": None,
            "required_unknown_conditions": [
                {"condition": "eligible merchant", "evidence": "selected merchants"},
            ],
        },
        {"transaction_amount": 600},
    )
    assert result["status"] == "NEEDS_MORE_INFORMATION"


def test_explicitly_excluded_bank_is_not_eligible() -> None:
    result = check_eligibility(
        {"excluded_banks": ["Example Bank"]},
        {"transaction_amount": 600, "bank": "example bank"},
    )
    assert result["status"] == "NOT_ELIGIBLE"
    assert result["failed"]


def test_all_known_mandatory_conditions_satisfied() -> None:
    result = check_eligibility(
        {
            "eligible_merchants": ["Shop"],
            "eligible_banks": ["Example Bank"],
            "minimum_transaction": 500,
            "new_user_required": True,
            "coupon_required": True,
            "activation_required": True,
        },
        {
            "merchant": "shop",
            "bank": "Example Bank",
            "transaction_amount": 600,
            "is_new_user": True,
            "coupon_applied": True,
            "offer_activated": True,
        },
    )
    assert result["status"] == "ELIGIBLE_BASED_ON_PROVIDED_RULES"
    assert not result["failed"]
    assert not result["missing"]


def test_missing_required_bank_needs_more_information() -> None:
    result = check_eligibility(
        {"eligible_banks": ["Example Bank"]},
        {"transaction_amount": 600},
    )
    assert result["status"] == "NEEDS_MORE_INFORMATION"
