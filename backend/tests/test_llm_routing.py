from app.config import Config
from app.utils.llm_routing import get_preferred_llm_endpoint


def test_preferred_llm_uses_boost_when_complete(monkeypatch):
    monkeypatch.setattr(Config, "LLM_API_KEY", "default-key")
    monkeypatch.setattr(Config, "LLM_BASE_URL", "https://default.example/v1")
    monkeypatch.setattr(Config, "LLM_MODEL_NAME", "default-model")
    monkeypatch.setattr(Config, "LLM_BOOST_API_KEY", "boost-key")
    monkeypatch.setattr(Config, "LLM_BOOST_BASE_URL", "https://boost.example/v1")
    monkeypatch.setattr(Config, "LLM_BOOST_MODEL_NAME", "boost-model")

    endpoint = get_preferred_llm_endpoint(prefer_boost=True)

    assert endpoint.api_key == "boost-key"
    assert endpoint.base_url == "https://boost.example/v1"
    assert endpoint.model == "boost-model"
    assert endpoint.is_boost is True


def test_preferred_llm_falls_back_when_boost_incomplete(monkeypatch):
    monkeypatch.setattr(Config, "LLM_API_KEY", "default-key")
    monkeypatch.setattr(Config, "LLM_BASE_URL", "https://default.example/v1")
    monkeypatch.setattr(Config, "LLM_MODEL_NAME", "default-model")
    monkeypatch.setattr(Config, "LLM_BOOST_API_KEY", "boost-key")
    monkeypatch.setattr(Config, "LLM_BOOST_BASE_URL", "")
    monkeypatch.setattr(Config, "LLM_BOOST_MODEL_NAME", "boost-model")

    endpoint = get_preferred_llm_endpoint(prefer_boost=True)

    assert endpoint.api_key == "default-key"
    assert endpoint.base_url == "https://default.example/v1"
    assert endpoint.model == "default-model"
    assert endpoint.is_boost is False


def test_preferred_llm_falls_back_when_boost_key_is_placeholder(monkeypatch):
    monkeypatch.setattr(Config, "LLM_API_KEY", "default-key")
    monkeypatch.setattr(Config, "LLM_BASE_URL", "https://default.example/v1")
    monkeypatch.setattr(Config, "LLM_MODEL_NAME", "default-model")
    monkeypatch.setattr(Config, "LLM_BOOST_API_KEY", "your_boost_api_key_here")
    monkeypatch.setattr(Config, "LLM_BOOST_BASE_URL", "https://boost.example/v1")
    monkeypatch.setattr(Config, "LLM_BOOST_MODEL_NAME", "boost-model")

    endpoint = get_preferred_llm_endpoint(prefer_boost=True)

    assert endpoint.api_key == "default-key"
    assert endpoint.model == "default-model"
    assert endpoint.is_boost is False
