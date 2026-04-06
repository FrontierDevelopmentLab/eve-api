"""Authentication handling for the EVE API client."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .exceptions import (
    AuthenticationError,
    NotAuthenticatedError,
    TokenExpiredError,
)
from .response import EveApiResponse


class EVEAuth:
    """Handles authentication and token management for the EVE API.

    This class manages the JWT token lifecycle including:
    - Initial login with email/password
    - Token storage and retrieval
    - Automatic token refresh when expired
    - Authorisation header generation

    Example:
        >>> auth = EVEAuth("https://api.eve-chat.chat")
        >>> await auth.login("user@example.com", "password")
        >>> headers = auth.get_headers()
    """

    # Buffer time before token expiry to trigger refresh (5 minutes)
    _REFRESH_BUFFER = timedelta(minutes=5)

    # Default token expiry if not provided (1 hour)
    _DEFAULT_EXPIRY = timedelta(hours=1)

    def __init__(self, base_url: str) -> None:
        """Initialise the authentication handler.

        Args:
            base_url: Base URL of the EVE API.
        """
        self.base_url = base_url.rstrip("/")
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self._token_expiry: datetime | None = None
        self._http_client: httpx.AsyncClient | None = None

    def set_http_client(self, client: httpx.AsyncClient) -> None:
        """Set the HTTP client for making requests.

        Args:
            client: httpx AsyncClient instance.
        """
        self._http_client = client

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create an HTTP client.

        Returns:
            httpx AsyncClient instance.
        """
        if self._http_client is not None:
            return self._http_client
        # Create a temporary client for auth requests
        return httpx.AsyncClient(base_url=self.base_url, timeout=30.0)

    async def login(self, email: str, password: str) -> None:
        """Authenticate with email and password.

        Args:
            email: User email address.
            password: User password.

        Raises:
            AuthenticationError: If login fails.
        """
        client = await self._get_client()
        should_close = self._http_client is None

        try:  # pylint: disable=too-many-try-statements
            response = await client.post(
                "/login",
                json={"email": email, "password": password},
            )

            if response.status_code == EveApiResponse.INVALID_CREDS.value:
                raise AuthenticationError("Invalid email or password")
            if response.status_code == EveApiResponse.FORBIDDEN.value:
                raise AuthenticationError("Account not activated")
            if response.status_code != EveApiResponse.SUCCESS.value:
                self._handle_error_response(response)

            data = response.json()
            self._store_tokens(data)

        finally:
            if should_close:
                await client.aclose()

    async def refresh(self) -> None:
        """Refresh the access token using the refresh token.

        Raises:
            TokenExpiredError: If refresh fails (e.g., refresh token expired).
            NotAuthenticatedError: If no refresh token is available.
        """
        if not self.refresh_token:
            raise NotAuthenticatedError(
                "No refresh token available. Please login first."
            )

        client = await self._get_client()
        should_close = self._http_client is None

        try:  # pylint: disable=too-many-try-statements
            response = await client.post(
                "/refresh",
                json={"refresh_token": self.refresh_token},
            )

            if response.status_code == EveApiResponse.INVALID_CREDS.value:
                # Refresh token expired
                self.access_token = None
                self.refresh_token = None
                self._token_expiry = None
                raise TokenExpiredError(
                    "Refresh token expired. Please login again."
                )
            if response.status_code != EveApiResponse.SUCCESS.value:
                self._handle_error_response(response)

            data = response.json()
            self.access_token = data.get("access_token")
            # Update expiry time
            self._token_expiry = (
                datetime.now(timezone.utc) + self._DEFAULT_EXPIRY
            )

        finally:
            if should_close:
                await client.aclose()

    def get_headers(self) -> dict[str, str]:
        """Get authorisation headers for API requests.

        Returns:
            Dictionary with Authorization header.

        Raises:
            NotAuthenticatedError: If not logged in.
        """
        if not self.access_token:
            raise NotAuthenticatedError(
                "Not authenticated. Please login first."
            )
        return {"Authorization": f"Bearer {self.access_token}"}

    async def ensure_authenticated(self) -> None:
        """Ensure the access token is valid, refreshing if necessary.

        This method should be called before making authenticated requests.
        It will automatically refresh the token if it is expired or about
        to expire.

        Raises:
            NotAuthenticatedError: If not logged in.
            TokenExpiredError: If token refresh fails.
        """
        if not self.access_token:
            raise NotAuthenticatedError(
                "Not authenticated. Please login first."
            )

        if self._should_refresh():
            await self.refresh()

    def is_authenticated(self) -> bool:
        """Check if currently authenticated.

        Returns:
            True if an access token is available.
        """
        return self.access_token is not None

    def _should_refresh(self) -> bool:
        """Check if the token should be refreshed.

        Returns:
            True if the token is expired or about to expire.
        """
        if not self._token_expiry:
            return False

        now = datetime.now(timezone.utc)
        return now >= (self._token_expiry - self._REFRESH_BUFFER)

    def _store_tokens(self, data: dict[str, Any]) -> None:
        """Store tokens from login/refresh response.

        Args:
            data: Response data containing tokens.
        """
        self.access_token = data.get("access_token")
        self.refresh_token = data.get("refresh_token", self.refresh_token)
        # Set expiry time (default 1 hour from now)
        self._token_expiry = datetime.now(timezone.utc) + self._DEFAULT_EXPIRY

    @staticmethod
    def _handle_error_response(response: httpx.Response) -> None:
        """Handle error responses from auth endpoints.

        Args:
            response: HTTP response.

        Raises:
            AuthenticationError: With details from response.
        """
        try:  # pylint: disable=too-many-try-statements
            data = response.json()
            message = data.get("detail", str(data))
        except Exception:  # pylint: disable=broad-exception-caught
            message = response.text or f"HTTP {response.status_code}"

        raise AuthenticationError(f"Authentication failed: {message}")

    def clear(self) -> None:
        """Clear all stored tokens."""
        self.access_token = None
        self.refresh_token = None
        self._token_expiry = None
