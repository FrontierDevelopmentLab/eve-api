"""This module contains an enum for response codes from EVE."""

from enum import Enum


class EveApiResponse(Enum):
    """Response code from EVE API."""

    SUCCESS = 200
    SUCCESS_NO_RESPONSE = 204
    BAD_REQUEST = 400
    INVALID_CREDS = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    INTERNAL_SERVER_ERROR = 500
