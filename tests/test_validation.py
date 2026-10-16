from io import BytesIO

import pytest
from PIL import Image

from model import OfferAnalysisError, analyze_offer, parse_model_response, validate_analysis
from ocr_utils import validate_image
from tools import parse_offer_date, to_decimal


def test_empty_offer_text_has_clear_validation_error() -> None:
    with pytest.raises(OfferAnalysisError, match="Enter offer text"):
        analyze_offer(" ")


def test_invalid_ai_json_is_reported_gracefully() -> None:
    with pytest.raises(OfferAnalysisError, match="invalid JSON"):
        parse_model_response("not JSON")


def test_ai_response_unknown_fields_are_normalized() -> None:
    result = validate_analysis({"facts": {"cashback_percentage": "10"}})
    assert result["facts"]["cashback_percentage"] == 10
    assert result["facts"]["maximum_cashback"] is None
    assert result["facts"]["expiry_date"] is None


def test_unmentioned_merchant_is_not_invented_as_a_mandatory_rule() -> None:
    result = validate_analysis(
        {
            "facts": {},
            "required_unknown_conditions": [
                {
                    "condition": "eligible merchants are missing",
                    "evidence": "Get 10% cashback",
                }
            ],
        },
        "Get 10% cashback",
    )
    assert result["required_unknown_conditions"] == []
    assert any("not used in eligibility" in item for item in result["interpretations"])


def test_invalid_ai_numbers_are_rejected() -> None:
    with pytest.raises(OfferAnalysisError, match="invalid number"):
        validate_analysis({"facts": {"maximum_cashback": -1}})


def test_invalid_numeric_input_is_rejected() -> None:
    with pytest.raises(ValueError):
        to_decimal("-1", "Transaction amount")


def test_offer_date_parse_handles_valid_and_invalid_dates() -> None:
    assert parse_offer_date("2026-10-16").isoformat() == "2026-10-16"
    assert parse_offer_date("not a date") is None


def test_empty_image_is_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        validate_image(b"")


def test_unsupported_or_invalid_image_is_rejected() -> None:
    with pytest.raises(ValueError, match="not a valid"):
        validate_image(b"not an image")


def test_unsupported_valid_image_format_is_rejected() -> None:
    buffer = BytesIO()
    Image.new("RGB", (2, 2)).save(buffer, format="BMP")
    with pytest.raises(ValueError, match="Only PNG and JPEG"):
        validate_image(buffer.getvalue())
