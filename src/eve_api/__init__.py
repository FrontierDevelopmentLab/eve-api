"""eve-api: Minimal authenticated HTTP client for the EVE API."""

from eve_api._version import __version__
from eve_api.client import EVEClient
from eve_api.exceptions import (
    APIError,
    AuthenticationError,
    EVEError,
    ForbiddenError,
    NotAuthenticatedError,
    NotFoundError,
    ServerError,
    StreamError,
    TokenExpiredError,
    ValidationError,
)

__all__ = [
    "__version__",
    "EVEClient",
    "EVEError",
    "APIError",
    "AuthenticationError",
    "ForbiddenError",
    "NotAuthenticatedError",
    "NotFoundError",
    "ServerError",
    "StreamError",
    "TokenExpiredError",
    "ValidationError",
]
