import json

import pytest

import model
from model import OfferAnalysisError


def test_analysis_uses_mocked_local_ollama_and_skills(monkeypatch) -> None:
    payload = {
        "facts": {"cashback_percentage": 10, "maximum_cashback": None},
        "interpretations": ["Ten percent cashback"],
        "missing_conditions": ["Maximum cashback is not stated"],
        "required_unknown_conditions": [
            {"condition": "eligible merchants", "evidence": "Selected merchants get 10% cashback"},
        ],
        "excerpts": ["10% cashback"],
    }
    prompts = []

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def chat(self, **kwargs):
            prompts.extend(message["content"] for message in kwargs["messages"])
            return {"message": {"content": json.dumps(payload)}}

    monkeypatch.setattr(model, "check_ollama", lambda: {
        "reachable": True, "model_available": True, "message": "ready",
    })
    monkeypatch.setattr(model.ollama, "Client", FakeClient)
    monkeypatch.setattr(model, "load_skills", lambda: "Test privacy rules")
    result = model.analyze_offer("Selected merchants get 10% cashback")
    assert result["facts"]["cashback_percentage"] == 10
    assert len(result["required_unknown_conditions"]) == 1
    assert "Test privacy rules" in prompts[0]
    assert "Selected merchants get 10% cashback" in prompts[0]


def test_unavailable_local_model_fails_without_fabricating_result(monkeypatch) -> None:
    monkeypatch.setattr(model, "check_ollama", lambda: {
        "reachable": False, "model_available": False, "message": "Start Ollama",
    })
    with pytest.raises(OfferAnalysisError, match="Start Ollama"):
        model.analyze_offer("10% cashback")
