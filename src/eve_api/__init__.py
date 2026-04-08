"""eve-api: Minimal authenticated HTTP client for the EVE API."""

from ._version import __version__
from .client import EVEClient
from .exceptions import (
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
