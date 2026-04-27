from __future__ import annotations
from unittest.mock import MagicMock, patch
import pytest


def test_chat_sends_correct_headers(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
    from core.openrouter_client import OpenRouterClient
    mock_response = MagicMock()
    mock_response.json.return_value = {"choices": [{"message": {"content": "hello"}}]}
    mock_response.raise_for_status = MagicMock()
    with patch("requests.post", return_value=mock_response) as mock_post:
        client = OpenRouterClient()
        result = client.chat([{"role": "user", "content": "hi"}])
    assert result == "hello"
    headers = mock_post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer test-key"
    assert headers["HTTP-Referer"] == "http://localhost:8000"
    assert headers["X-Title"] == "CPA-Agent"
    assert mock_post.call_args.kwargs["json"]["model"] == "nvidia/nemotron-3-super-120b-a12b:free"


def test_chat_raises_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    from core.openrouter_client import OpenRouterClient
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        OpenRouterClient().chat([{"role": "user", "content": "hi"}])


def test_default_model_is_nemotron(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    from core.openrouter_client import OpenRouterClient
    assert OpenRouterClient().model == "nvidia/nemotron-3-super-120b-a12b:free"
