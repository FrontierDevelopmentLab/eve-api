"""Minimal authenticated HTTP client for the EVE API."""

from __future__ import annotations

import json as _json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .auth import EVEAuth
from .exceptions import (
    APIError,
    ForbiddenError,
    NotFoundError,
    ServerError,
    StreamError,
    ValidationError,
)
from .response import EveApiResponse


class EVEClient:
    """Minimal authenticated HTTP client for the EVE (Earth Virtual Expert) API.

    Provides login, automatic token refresh, and generic HTTP methods that
    return plain dicts. No domain-specific wrappers or Pydantic models.

    Example:
        >>> from eve_api import EVEClient
        >>>
        >>> async with EVEClient() as eve:
        ...     await eve.login("user@example.com", "password")
        ...     user = await eve.get("/users/me")
        ...     print(user["email"])
        ...
        ...     conv = await eve.post("/conversations", json={"name": "Test"})
        ...     print(conv["id"])
    """

    _DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        base_url: str = "https://api.eve-chat.chat",
        timeout: float | None = None,
    ) -> None:
        """Initialise the EVE client.

        Args:
            base_url: Base URL of the EVE API.
            timeout: Default timeout for requests in seconds.
        """
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout or self._DEFAULT_TIMEOUT
        self.auth = EVEAuth(self.base_url)
        self._http: httpx.AsyncClient | None = None
        self._owns_http_client = False

    async def __aenter__(self) -> EVEClient:
        """Enter async context and initialise HTTP client."""
        await self._ensure_http_client()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit async context and clean up resources."""
        await self.close()

    async def _ensure_http_client(self) -> None:
        """Ensure HTTP client is initialised."""
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self._timeout,
            )
            self._owns_http_client = True
            self.auth.set_http_client(self._http)

    async def close(self) -> None:
        """Close the HTTP client and clean up resources."""
        if self._http is not None and self._owns_http_client:
            await self._http.aclose()
            self._http = None
            self._owns_http_client = False

    # Authentication

    async def login(self, email: str, password: str) -> None:
        """Authenticate with email and password.

        Args:
            email: User email address.
            password: User password.

        Raises:
            AuthenticationError: If login fails.
        """
        await self._ensure_http_client()
        await self.auth.login(email, password)

    def is_authenticated(self) -> bool:
        """Check if the client is authenticated."""
        return self.auth.is_authenticated()

    @property
    def token(self) -> str | None:
        """Current access token, or None if not authenticated."""
        return self.auth.access_token

    @property
    def auth_headers(self) -> dict[str, str]:
        """Authorisation headers for use with external HTTP clients.

        Returns:
            Dictionary with Authorization header.

        Raises:
            NotAuthenticatedError: If not logged in.
        """
        return self.auth.get_headers()

    # Convenience HTTP methods

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Make an authenticated GET request.

        Args:
            path: API path (e.g., "/users/me").
            params: Query parameters.
            timeout: Request timeout override.

        Returns:
            Parsed JSON response (dict or list).
        """
        response = await self.request(
            "GET", path, params=params, timeout=timeout
        )
        return response.json()

    async def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Make an authenticated POST request.

        Args:
            path: API path.
            json: JSON request body.
            params: Query parameters.
            timeout: Request timeout override.

        Returns:
            Parsed JSON response (dict or list).
        """
        response = await self.request(
            "POST", path, json=json, params=params, timeout=timeout
        )
        return response.json()

    async def patch(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Make an authenticated PATCH request.

        Args:
            path: API path.
            json: JSON request body.
            params: Query parameters.
            timeout: Request timeout override.

        Returns:
            Parsed JSON response (dict or list).
        """
        response = await self.request(
            "PATCH", path, json=json, params=params, timeout=timeout
        )
        return response.json()

    async def delete(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Make an authenticated DELETE request.

        Args:
            path: API path.
            params: Query parameters.
            timeout: Request timeout override.

        Returns:
            Parsed JSON response (dict or list), or None for 204 responses.
        """
        response = await self.request(
            "DELETE", path, params=params, timeout=timeout
        )
        if response.status_code == EveApiResponse.SUCCESS_NO_RESPONSE.value:
            return None
        return response.json()

    async def stream(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        method: str = "POST",
        timeout: float | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Make an authenticated streaming request, yielding parsed SSE events.

        Args:
            path: API path.
            json: JSON request body.
            method: HTTP method (default: POST).
            timeout: Request timeout override.

        Yields:
            Parsed SSE event dicts.

        Raises:
            StreamError: If streaming fails or SSE data cannot be parsed.
            APIError: If the server returns an error status.
        """
        await self._ensure_http_client()
        await self.auth.ensure_authenticated()

        url = f"{self.base_url}{path}"
        headers = self.auth.get_headers()
        headers["Accept"] = "text/event-stream"

        async with self._http.stream(  # type: ignore[union-attr]
            method,
            url,
            json=json,
            headers=headers,
            timeout=timeout or 300.0,
        ) as response:
            if response.status_code >= EveApiResponse.BAD_REQUEST.value:
                await response.aread()
                self._handle_error(response)

            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue

                if (  # pylint: disable=magic-value-comparison
                    data_str := line[6:]
                ) == "[DONE]":
                    return

                try:
                    event = _json.loads(data_str)
                except _json.JSONDecodeError as e:
                    raise StreamError(f"Failed to parse SSE data: {e}") from e

                yield event

                # Stop on terminal events
                if event.get("type", "") in {
                    "final",
                    "error",
                    "stopped",
                }:
                    return

    # Low-level request method

    async def request(  # pylint: disable=too-many-positional-arguments
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        timeout: float | None = None,
        auth_required: bool = True,
    ) -> httpx.Response:
        """Make an HTTP request, returning the raw httpx.Response.

        Args:
            method: HTTP method.
            path: API path (appended to base_url).
            params: Query parameters.
            json: JSON request body.
            timeout: Request timeout override.
            auth_required: Whether to include auth headers (default: True).

        Returns:
            Raw httpx.Response.

        Raises:
            NotAuthenticatedError: If auth_required and not logged in.
            APIError: If the response status is >= 400.
        """
        await self._ensure_http_client()

        url = f"{self.base_url}{path}"
        headers: dict[str, str] = {}

        if auth_required:
            await self.auth.ensure_authenticated()
            headers = self.auth.get_headers()

        response = await self._http.request(  # type: ignore[union-attr]
            method=method,
            url=url,
            params=params,
            json=json,
            headers=headers,
            timeout=timeout or self._timeout,
        )

        if response.status_code >= EveApiResponse.BAD_REQUEST.value:
            self._handle_error(response)

        return response

    @staticmethod
    def _handle_error(response: httpx.Response) -> None:
        """Handle error responses.

        Args:
            response: HTTP response with error status.

        Raises:
            NotFoundError: For 404 responses.
            ForbiddenError: For 403 responses.
            ValidationError: For 400 responses.
            ServerError: For 5xx responses.
            APIError: For other error responses.
        """
        status = response.status_code

        try:  # pylint: disable=too-many-try-statements
            data = response.json()
            message = data.get("detail", str(data))
            if isinstance(message, list):
                message = "; ".join(str(e) for e in message)
        except Exception:  # pylint: disable=broad-exception-caught
            message = response.text or f"HTTP {status}"

        if status == EveApiResponse.NOT_FOUND.value:
            raise NotFoundError("resource", "unknown")
        if status == EveApiResponse.FORBIDDEN.value:
            raise ForbiddenError(message)
        if status == EveApiResponse.BAD_REQUEST.value:
            raise ValidationError(message)
        if status >= EveApiResponse.INTERNAL_SERVER_ERROR.value:
            raise ServerError(message, status_code=status)
        raise APIError(message, status_code=status)
