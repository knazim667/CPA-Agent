from __future__ import annotations
from unittest.mock import patch, MagicMock


def test_openrouter_provider_returns_openrouter_client(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    mock_openrouter = MagicMock()
    with patch("core.model_client.OpenRouterClient", mock_openrouter):
        from core.model_client import get_model_client
        result = get_model_client(purpose="reasoning", reasoning_mode="fast")

    mock_openrouter.assert_called_once()
    assert result == mock_openrouter.return_value


def test_openai_provider_returns_openai_client(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai")

    mock_openai = MagicMock()
    with patch("core.model_client.OpenAIClient", mock_openai):
        from core.model_client import get_model_client
        result = get_model_client(purpose="reasoning", reasoning_mode="fast")

    mock_openai.assert_called_once()
    assert result == mock_openai.return_value
