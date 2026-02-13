"""Pytest configuration and fixtures for eve-api tests."""

import pytest
import respx
from httpx import Response

from eve_api import EVEClient


@pytest.fixture
def base_url() -> str:
    """Return the test API base URL."""
    return "https://test.eve.example.com"


@pytest.fixture
def mock_api(base_url: str):
    """Create a mock API context for testing."""
    with respx.mock(base_url=base_url, assert_all_called=False) as mock:
        yield mock


@pytest.fixture
async def client(base_url: str):
    """Create an EVE client for testing."""
    async with EVEClient(base_url) as client:
        yield client


@pytest.fixture
async def authenticated_client(mock_api, client: EVEClient):
    """Create an authenticated EVE client for testing."""
    mock_api.post("/login").mock(return_value=Response(200, json={
        "access_token": "test-access-token",
        "refresh_token": "test-refresh-token",
    }))
    await client.login("test@example.com", "password")
    return client
