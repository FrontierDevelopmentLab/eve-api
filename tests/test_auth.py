"""Tests for the EVEAuth."""

from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from eve_api.auth import (
    AuthenticationError,
    EVEAuth,
    NotAuthenticatedError,
    TokenExpiredError,
)

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


def make_auth(*, access_token=None, refresh_token=None, http_client=None):
    """Return an Auth instance with controllable initial state."""
    auth = EVEAuth("https://example.com")
    auth.access_token = access_token
    auth.refresh_token = refresh_token
    auth._http_client = http_client  # pylint: disable=protected-access
    return auth


def make_response(status_code: int, json_data=None, text=""):
    """Build a minimal httpx.Response-like mock."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.text = text
    response.json.return_value = json_data if json_data is not None else {}
    return response


# ---------------------------------------------------------------------------
# Auth._get_client
# ---------------------------------------------------------------------------


class TestGetClient:
    """Tests for Auth._get_client."""

    @pytest.mark.asyncio
    @staticmethod
    async def test_returns_existing_client_when_set():
        """When _http_client is already set, it is returned directly."""
        existing = MagicMock(spec=httpx.AsyncClient)
        auth = make_auth(http_client=existing)
        result = await auth._get_client()  # pylint: disable=protected-access
        assert result is existing

    @pytest.mark.asyncio
    @staticmethod
    async def test_creates_temporary_client_when_none():
        """When _http_client is None a fresh AsyncClient is created and returned."""
        auth = make_auth(http_client=None)
        mock_instance = MagicMock(spec=httpx.AsyncClient)
        with patch("eve_api.auth.httpx.AsyncClient") as mock_client:
            mock_client.return_value = mock_instance
            result = (
                await auth._get_client()  # pylint: disable=protected-access
            )
        mock_client.assert_called_once_with(
            base_url=auth.base_url, timeout=30.0
        )
        assert result is mock_instance


# ---------------------------------------------------------------------------
# Auth.login
# ---------------------------------------------------------------------------


class TestLogin:
    """Tests for Auth.login."""

    @pytest.mark.asyncio
    @staticmethod
    async def test_login_unexpected_status_calls_handle_error():
        """A non-success, non-401, non-403 status code triggers _handle_error_response."""
        auth = make_auth()
        response = make_response(HTTPStatus.INTERNAL_SERVER_ERROR)

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = response

        with (
            patch.object(auth, "_get_client", return_value=mock_client),
            patch.object(
                auth,
                "_handle_error_response",
                side_effect=AuthenticationError("err"),
            ) as mock_handle,
        ):
            with pytest.raises(AuthenticationError, match="err"):
                await auth.login("user@example.com", "pw")

        mock_handle.assert_called_once_with(response)

    @pytest.mark.asyncio
    @staticmethod
    async def test_login_closes_temporary_client_on_success():
        """When no persistent client exists the temporary client is closed after login."""
        auth = make_auth(
            http_client=None
        )  # no persistent client → should_close = True
        response = make_response(
            HTTPStatus.OK,
            json_data={"access_token": "tok", "refresh_token": "ref"},
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = response

        with patch.object(auth, "_get_client", return_value=mock_client):
            await auth.login("user@example.com", "pw")

        mock_client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    @staticmethod
    async def test_login_closes_temporary_client_on_error():
        """The temporary client is closed even when login raises an exception."""
        auth = make_auth(http_client=None)
        response = make_response(HTTPStatus.UNAUTHORIZED)

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = response

        with patch.object(auth, "_get_client", return_value=mock_client):
            with pytest.raises(AuthenticationError):
                await auth.login("bad@example.com", "bad")

        mock_client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    @staticmethod
    async def test_login_does_not_close_persistent_client():
        """When a persistent client is supplied it is NOT closed after login."""
        persistent = AsyncMock(spec=httpx.AsyncClient)
        auth = make_auth(http_client=persistent)
        response = make_response(
            HTTPStatus.OK,
            json_data={"access_token": "tok", "refresh_token": "ref"},
        )
        persistent.post.return_value = response

        await auth.login("user@example.com", "pw")

        persistent.aclose.assert_not_awaited()


# ---------------------------------------------------------------------------
# Auth.refresh
# ---------------------------------------------------------------------------


class TestRefresh:
    """Full coverage for Auth.refresh."""

    @pytest.mark.asyncio
    @staticmethod
    async def test_refresh_raises_when_no_refresh_token():
        """Test that refresh method raises NotAuthenticatedError
        when no refresh token available."""
        auth = make_auth()
        with pytest.raises(
            NotAuthenticatedError, match="No refresh token available"
        ):
            await auth.refresh()

    @pytest.mark.asyncio
    @staticmethod
    async def test_refresh_clears_tokens_on_expired_refresh_token():
        """Test that refresh clears token on expired refresh token."""
        auth = make_auth(
            access_token="old_access", refresh_token="expired_ref"
        )
        response = make_response(HTTPStatus.UNAUTHORIZED)

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = response

        with patch.object(auth, "_get_client", return_value=mock_client):
            with pytest.raises(
                TokenExpiredError, match="Refresh token expired"
            ):
                await auth.refresh()

        assert auth.access_token is None
        assert auth.refresh_token is None
        assert auth._token_expiry is None  # pylint: disable=protected-access

    @pytest.mark.asyncio
    @staticmethod
    async def test_refresh_unexpected_status_calls_handle_error():
        """Test that refresh on unexpected status calls _handle_error."""
        auth = make_auth(refresh_token="ref")
        response = make_response(500)

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = response

        with (
            patch.object(auth, "_get_client", return_value=mock_client),
            patch.object(
                auth,
                "_handle_error_response",
                side_effect=AuthenticationError("boom"),
            ) as mock_handle,
        ):
            with pytest.raises(AuthenticationError, match="boom"):
                await auth.refresh()

        mock_handle.assert_called_once_with(response)

    @pytest.mark.asyncio
    @staticmethod
    async def test_refresh_updates_access_token_and_expiry_on_success():
        """Test that refresh updates access token and expiry on success."""
        auth = make_auth(refresh_token="ref")
        tok = "new_tok"
        response = make_response(
            HTTPStatus.OK,
            json_data={"access_token": tok},
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = response

        before = datetime.now(timezone.utc)
        with patch.object(auth, "_get_client", return_value=mock_client):
            await auth.refresh()
        after = datetime.now(timezone.utc)

        assert auth.access_token == tok
        assert (
            auth._token_expiry is not None  # pylint: disable=protected-access
        )
        assert (
            before
            < auth._token_expiry  # pylint: disable=protected-access
            <= after
            + EVEAuth._DEFAULT_EXPIRY  # pylint: disable=protected-access
        )

    @pytest.mark.asyncio
    @staticmethod
    async def test_refresh_closes_temporary_client():
        """Test refresh closes temporary client."""
        auth = make_auth(http_client=None, refresh_token="ref")
        response = make_response(
            HTTPStatus.OK,
            json_data={"access_token": "new_tok"},
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = response

        with patch.object(auth, "_get_client", return_value=mock_client):
            await auth.refresh()

        mock_client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    @staticmethod
    async def test_refresh_closes_temporary_client_on_error():
        """Test refresh closes temporary client on error."""
        auth = make_auth(http_client=None, refresh_token="ref")
        response = make_response(HTTPStatus.UNAUTHORIZED)

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = response

        with patch.object(auth, "_get_client", return_value=mock_client):
            with pytest.raises(TokenExpiredError):
                await auth.refresh()

        mock_client.aclose.assert_awaited_once()


# ---------------------------------------------------------------------------
# Auth.get_headers
# ---------------------------------------------------------------------------


class TestGetHeaders:
    """Tests for Auth.get_headers."""

    @staticmethod
    def test_raises_when_not_authenticated():
        """Raises NotAuthenticatedError when access_token is None."""
        auth = make_auth()
        with pytest.raises(NotAuthenticatedError, match="Not authenticated"):
            auth.get_headers()

    @staticmethod
    def test_returns_bearer_header_when_authenticated():
        """Test GET returns bearer token when authenticated."""
        auth = make_auth(access_token="mytoken")
        assert auth.get_headers() == {"Authorization": "Bearer mytoken"}


# ---------------------------------------------------------------------------
# Auth.ensure_authenticated
# ---------------------------------------------------------------------------


class TestEnsureAuthenticated:
    """Tests for Auth.ensure_authenticated."""

    @pytest.mark.asyncio
    @staticmethod
    async def test_calls_refresh_when_token_should_be_refreshed():
        """When _should_refresh() returns True, refresh() is awaited."""
        auth = make_auth(access_token="tok")

        with (
            patch.object(auth, "_should_refresh", return_value=True),
            patch.object(
                auth, "refresh", new_callable=AsyncMock
            ) as mock_refresh,
        ):
            await auth.ensure_authenticated()

        mock_refresh.assert_awaited_once()

    @pytest.mark.asyncio
    @staticmethod
    async def test_does_not_refresh_when_token_is_fresh():
        """Test that it does not refresh when token is fresh."""
        auth = make_auth(access_token="tok")

        with (
            patch.object(auth, "_should_refresh", return_value=False),
            patch.object(
                auth, "refresh", new_callable=AsyncMock
            ) as mock_refresh,
        ):
            await auth.ensure_authenticated()

        mock_refresh.assert_not_awaited()

    @pytest.mark.asyncio
    @staticmethod
    async def test_raises_when_no_access_token():
        """Test that NotAuthenticatedError is raised when no
        access token is available."""
        auth = make_auth()
        with pytest.raises(NotAuthenticatedError):
            await auth.ensure_authenticated()


# ---------------------------------------------------------------------------
# Auth._should_refresh
# ---------------------------------------------------------------------------


class TestShouldRefresh:
    """Tests for Auth._should_refresh, including the no-expiry branch."""

    @staticmethod
    def test_returns_false_when_no_token_expiry():
        """When _token_expiry is None the method returns False without error."""
        auth = make_auth()
        assert auth._token_expiry is None  # pylint: disable=protected-access
        assert (
            auth._should_refresh() is False  # pylint: disable=protected-access
        )

    @staticmethod
    def test_returns_true_when_expiry_is_past():
        """Test that _should_refresh returns True when token is expired."""
        auth = make_auth()
        auth._token_expiry = datetime.now(  # pylint: disable=protected-access
            timezone.utc
        ) - timedelta(seconds=1)
        assert (
            auth._should_refresh() is True  # pylint: disable=protected-access
        )

    @staticmethod
    def test_returns_false_when_expiry_is_far_future():
        """Test that _should_refresh returns False when expiry is
        far into the future."""
        auth = make_auth()
        auth._token_expiry = datetime.now(  # pylint: disable=protected-access
            timezone.utc
        ) + timedelta(hours=1)
        assert (
            auth._should_refresh() is False  # pylint: disable=protected-access
        )

    @staticmethod
    def test_returns_true_within_refresh_buffer():
        """Token inside the REFRESH_BUFFER window should trigger a refresh."""
        auth = make_auth()
        # Set expiry just inside the buffer so now >= expiry - buffer
        auth._token_expiry = (  # pylint: disable=protected-access
            datetime.now(timezone.utc)
            + EVEAuth._REFRESH_BUFFER  # pylint: disable=protected-access
            - timedelta(seconds=1)
        )
        assert (
            auth._should_refresh() is True  # pylint: disable=protected-access
        )


# ---------------------------------------------------------------------------
# Auth._handle_error_response
# ---------------------------------------------------------------------------


class TestHandleErrorResponse:
    """Tests for the static _handle_error_response method."""

    @staticmethod
    def test_raises_with_detail_from_json():
        """Test _handle_error_response raises AuthenticationError with details."""
        response = make_response(
            HTTPStatus.BAD_REQUEST,
            json_data={"detail": "Bad thing happened"},
        )
        with pytest.raises(AuthenticationError, match="Bad thing happened"):
            EVEAuth._handle_error_response(  # pylint: disable=protected-access
                response
            )

    @staticmethod
    def test_raises_with_stringified_json_when_no_detail_key():
        """Test _handle_error_response raises AuthenticationError when no detail key."""
        response = make_response(
            HTTPStatus.BAD_REQUEST, json_data={"error": "nope"}
        )
        with pytest.raises(AuthenticationError, match="Authentication failed"):
            EVEAuth._handle_error_response(  # pylint: disable=protected-access
                response
            )

    @staticmethod
    def test_falls_back_to_response_text_when_json_fails():
        """Test fallback to response text when JSON fails."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = HTTPStatus.SERVICE_UNAVAILABLE
        response.text = "Service Unavailable"
        response.json.side_effect = ValueError("not json")
        with pytest.raises(AuthenticationError, match="Service Unavailable"):
            EVEAuth._handle_error_response(  # pylint: disable=protected-access
                response
            )

    @staticmethod
    def test_falls_back_to_status_code_when_text_is_empty():
        """Test fallback to status code when text is empty."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = HTTPStatus.SERVICE_UNAVAILABLE
        response.text = ""
        response.json.side_effect = ValueError("not json")
        with pytest.raises(
            AuthenticationError,
            match=f"HTTP {HTTPStatus.SERVICE_UNAVAILABLE}",
        ):
            EVEAuth._handle_error_response(  # pylint: disable=protected-access
                response
            )


# ---------------------------------------------------------------------------
# Auth.clear
# ---------------------------------------------------------------------------


class TestClear:
    """Tests for Auth.clear."""

    @staticmethod
    def test_clear_resets_all_tokens():
        """Test that clear resets all tokens."""
        auth = make_auth(access_token="tok", refresh_token="ref")
        auth._token_expiry = datetime.now(  # pylint: disable=protected-access
            timezone.utc
        )

        auth.clear()

        assert auth.access_token is None
        assert auth.refresh_token is None
        assert auth._token_expiry is None  # pylint: disable=protected-access

    @staticmethod
    def test_clear_is_idempotent():
        """Calling clear() on an already-cleared instance does not raise."""
        auth = make_auth()
        auth.clear()  # should not raise
        assert auth.access_token is None
