import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from algokitforge.core.pushover_mgr import PushoverManager

@pytest.mark.asyncio
async def test_pushover_send_success():
    """Test successful Pushover notification."""
    with patch.dict("os.environ", {"PUSHOVER_USER_KEY": "user123", "PUSHOVER_API_TOKEN": "token123"}):
        mgr = PushoverManager()
        
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        
        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_response)) as mock_post:
            success = await mgr.send_notification("Hello", title="Test")
            assert success is True
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            assert kwargs["data"]["message"] == "Hello"
            assert kwargs["data"]["user"] == "user123"

@pytest.mark.asyncio
async def test_pushover_send_missing_creds():
    """Test failure when credentials are missing."""
    with patch.dict("os.environ", {}, clear=True):
        mgr = PushoverManager()
        mgr.user_key = None
        mgr.api_token = None
        
        success = await mgr.send_notification("Hello")
        assert success is False

@pytest.mark.asyncio
async def test_pushover_send_failure():
    """Test failure when API returns error."""
    with patch.dict("os.environ", {"PUSHOVER_USER_KEY": "user123", "PUSHOVER_API_TOKEN": "token123"}):
        mgr = PushoverManager()
        
        with patch("httpx.AsyncClient.post", AsyncMock(side_effect=Exception("API Error"))):
            success = await mgr.send_notification("Hello")
            assert success is False
