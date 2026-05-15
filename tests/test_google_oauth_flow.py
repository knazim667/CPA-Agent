from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch
from core.google_auth import GoogleWorkspaceAuth


def test_build_web_auth_url_returns_string():
    mock_flow = MagicMock()
    mock_flow.authorization_url.return_value = ("https://accounts.google.com/o/oauth2/auth?foo=bar", "state123")
    with patch("core.google_auth.Flow") as MockFlow:
        MockFlow.from_client_config.return_value = mock_flow
        url = GoogleWorkspaceAuth.build_web_auth_url(
            client_id="cid", client_secret="csec",
            redirect_uri="http://localhost/callback",
            state="state123",
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
    assert url.startswith("https://accounts.google.com")


def test_exchange_web_auth_code_returns_credentials():
    mock_creds = MagicMock()
    mock_flow = MagicMock()
    mock_flow.credentials = mock_creds
    with patch("core.google_auth.Flow") as MockFlow:
        MockFlow.from_client_config.return_value = mock_flow
        result = GoogleWorkspaceAuth.exchange_web_auth_code(
            client_id="cid", client_secret="csec",
            redirect_uri="http://localhost/callback",
            state="state123",
            code="auth_code_xyz",
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
    mock_flow.fetch_token.assert_called_once_with(code="auth_code_xyz")
    assert result is mock_creds


def test_token_path_overrides_default():
    auth = GoogleWorkspaceAuth(token_path="/tmp/my_tokens.json")
    assert auth.oauth_token_path == "/tmp/my_tokens.json"


def test_from_token_path_sets_auth():
    from skills.google_sheets_manager import GoogleSheetsManager
    manager = GoogleSheetsManager.from_token_path("/tmp/biz_tokens.json")
    assert manager.auth.oauth_token_path == "/tmp/biz_tokens.json"
    assert manager._service is None
