"""Custom exceptions for the EVE API client."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any


class EVEError(Exception):
    """Base exception for all EVE API client errors."""

    def __init__(
        self, message: str, details: dict[str, Any] | None = None
    ) -> None:
        """Initialise the error.

        Args:
            message: Human-readable error message.
            details: Additional error details.
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AuthenticationError(EVEError):
    """Raised when authentication fails."""


class TokenExpiredError(AuthenticationError):
    """Raised when the access token has expired and refresh failed."""


class NotAuthenticatedError(AuthenticationError):
    """Raised when attempting an operation that requires authentication."""


class APIError(EVEError):
    """Raised when the API returns an error response."""

    def __init__(
        self,
        message: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialise the API error.

        Args:
            message: Human-readable error message.
            status_code: HTTP status code from the response.
            details: Additional error details from the response body.
        """
        super().__init__(message, details)
        self.status_code = status_code


class NotFoundError(APIError):
    """Raised when a requested resource is not found (404)."""

    def __init__(
        self,
        message: str = "Resource not found",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialise the not found error.

        Args:
            message: Human-readable error message (typically the server's
                ``detail`` field).
            details: Additional error details from the response body.
        """
        super().__init__(
            message,
            status_code=HTTPStatus.NOT_FOUND,
            details=details,
        )


class ForbiddenError(APIError):
    """Raised when access to a resource is forbidden (403)."""

    def __init__(self, message: str = "Access forbidden") -> None:
        """Initialise the forbidden error.

        Args:
            message: Human-readable error message.
        """
        super().__init__(message, status_code=HTTPStatus.FORBIDDEN)


class ValidationError(APIError):
    """Raised when request validation fails (400)."""

    def __init__(
        self, message: str, details: dict[str, Any] | None = None
    ) -> None:
        """Initialise the validation error.

        Args:
            message: Human-readable error message.
            details: Validation error details.
        """
        super().__init__(
            message,
            status_code=HTTPStatus.BAD_REQUEST,
            details=details,
        )


class ServerError(APIError):
    """Raised when the server returns a 5xx error."""

    def __init__(
        self,
        message: str = "Internal server error",
        status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialise the server error.

        Args:
            message: Human-readable error message.
            status_code: HTTP status code (5xx).
            details: Additional error details.
        """
        super().__init__(message, status_code=status_code, details=details)


class StreamError(EVEError):
    """Raised when an error occurs during streaming."""
