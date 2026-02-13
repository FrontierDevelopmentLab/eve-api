"""Tests for the EVEClient."""

import json

import pytest
import respx
from httpx import Response

from eve_api import (
    APIError,
    AuthenticationError,
    EVEClient,
    ForbiddenError,
    NotAuthenticatedError,
    NotFoundError,
    ServerError,
    StreamError,
    ValidationError,
)


# --- Authentication ---


async def test_login_success(mock_api, client: EVEClient):
    mock_api.post("/login").mock(return_value=Response(200, json={
        "access_token": "tok-123",
        "refresh_token": "ref-456",
    }))

    await client.login("user@example.com", "password")

    assert client.is_authenticated()
    assert client.token == "tok-123"
    assert client.auth_headers == {"Authorization": "Bearer tok-123"}


async def test_login_invalid_credentials(mock_api, client: EVEClient):
    mock_api.post("/login").mock(return_value=Response(401, json={
        "detail": "Invalid credentials",
    }))

    with pytest.raises(AuthenticationError, match="Invalid email or password"):
        await client.login("bad@example.com", "wrong")

    assert not client.is_authenticated()


async def test_login_account_not_activated(mock_api, client: EVEClient):
    mock_api.post("/login").mock(return_value=Response(403, json={
        "detail": "Account not activated",
    }))

    with pytest.raises(AuthenticationError, match="Account not activated"):
        await client.login("user@example.com", "password")


async def test_not_authenticated_error(client: EVEClient):
    with pytest.raises(NotAuthenticatedError):
        await client.get("/users/me")


async def test_token_property_none_before_login(client: EVEClient):
    assert client.token is None


# --- GET ---


async def test_get(mock_api, authenticated_client: EVEClient):
    mock_api.get("/users/me").mock(return_value=Response(200, json={
        "id": "user-1",
        "email": "test@example.com",
    }))

    data = await authenticated_client.get("/users/me")

    assert data["id"] == "user-1"
    assert data["email"] == "test@example.com"


async def test_get_with_params(mock_api, authenticated_client: EVEClient):
    mock_api.get("/collections/public").mock(return_value=Response(200, json={
        "data": [{"id": "c-1", "name": "Public"}],
        "meta": {"total_count": 1},
    }))

    data = await authenticated_client.get("/collections/public", params={"page": 1})

    assert len(data["data"]) == 1
    assert data["data"][0]["name"] == "Public"


# --- POST ---


async def test_post(mock_api, authenticated_client: EVEClient):
    mock_api.post("/conversations").mock(return_value=Response(201, json={
        "id": "conv-1",
        "name": "New Chat",
    }))

    data = await authenticated_client.post("/conversations", json={"name": "New Chat"})

    assert data["id"] == "conv-1"
    assert data["name"] == "New Chat"


# --- PATCH ---


async def test_patch(mock_api, authenticated_client: EVEClient):
    mock_api.patch("/conversations/conv-1").mock(return_value=Response(200, json={
        "id": "conv-1",
        "name": "Renamed",
    }))

    data = await authenticated_client.patch(
        "/conversations/conv-1", json={"name": "Renamed"}
    )

    assert data["name"] == "Renamed"


# --- DELETE ---


async def test_delete(mock_api, authenticated_client: EVEClient):
    mock_api.delete("/conversations/conv-1").mock(return_value=Response(204))

    result = await authenticated_client.delete("/conversations/conv-1")

    assert result is None


async def test_delete_with_body(mock_api, authenticated_client: EVEClient):
    mock_api.delete("/conversations/conv-1").mock(return_value=Response(200, json={
        "deleted": True,
    }))

    result = await authenticated_client.delete("/conversations/conv-1")

    assert result["deleted"] is True


# --- request() with auth_required=False ---


async def test_request_no_auth(mock_api, client: EVEClient):
    mock_api.get("/health").mock(return_value=Response(200, json={"status": "ok"}))

    response = await client.request("GET", "/health", auth_required=False)

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


# --- Error handling ---


async def test_404_raises_not_found(mock_api, authenticated_client: EVEClient):
    mock_api.get("/conversations/missing").mock(return_value=Response(404, json={
        "detail": "Not found",
    }))

    with pytest.raises(NotFoundError):
        await authenticated_client.get("/conversations/missing")


async def test_403_raises_forbidden(mock_api, authenticated_client: EVEClient):
    mock_api.get("/admin/users").mock(return_value=Response(403, json={
        "detail": "Forbidden",
    }))

    with pytest.raises(ForbiddenError):
        await authenticated_client.get("/admin/users")


async def test_400_raises_validation_error(mock_api, authenticated_client: EVEClient):
    mock_api.post("/conversations").mock(return_value=Response(400, json={
        "detail": "name is required",
    }))

    with pytest.raises(ValidationError, match="name is required"):
        await authenticated_client.post("/conversations", json={})


async def test_500_raises_server_error(mock_api, authenticated_client: EVEClient):
    mock_api.get("/broken").mock(return_value=Response(500, json={
        "detail": "Internal server error",
    }))

    with pytest.raises(ServerError):
        await authenticated_client.get("/broken")


async def test_422_raises_api_error(mock_api, authenticated_client: EVEClient):
    mock_api.post("/conversations").mock(return_value=Response(422, json={
        "detail": [{"msg": "field required", "type": "missing"}],
    }))

    with pytest.raises(APIError) as exc_info:
        await authenticated_client.post("/conversations", json={})

    assert exc_info.value.status_code == 422


# --- Streaming ---


def _sse_response(*events: dict, done: bool = True) -> Response:
    """Build a Response whose body is SSE-formatted lines."""
    lines = []
    for event in events:
        lines.append(f"data: {json.dumps(event)}\n\n")
    if done:
        lines.append("data: [DONE]\n\n")
    body = "".join(lines)
    return Response(
        200,
        content=body.encode(),
        headers={"content-type": "text/event-stream"},
    )


async def test_stream(mock_api, authenticated_client: EVEClient):
    events = [
        {"type": "status", "content": "Searching..."},
        {"type": "token", "content": "Hello"},
        {"type": "token", "content": " world"},
        {"type": "final", "content": "Hello world", "message_id": "m-1"},
    ]
    mock_api.post("/conversations/c-1/stream_messages").mock(
        return_value=_sse_response(*events)
    )

    collected = []
    async for event in authenticated_client.stream(
        "/conversations/c-1/stream_messages",
        json={"query": "Hello"},
    ):
        collected.append(event)

    # Should stop after "final" event
    assert len(collected) == 4
    assert collected[0]["type"] == "status"
    assert collected[-1]["type"] == "final"


async def test_stream_stops_on_error_event(mock_api, authenticated_client: EVEClient):
    events = [
        {"type": "token", "content": "partial"},
        {"type": "error", "content": "Something went wrong"},
    ]
    mock_api.post("/conversations/c-1/stream_messages").mock(
        return_value=_sse_response(*events, done=False)
    )

    collected = []
    async for event in authenticated_client.stream(
        "/conversations/c-1/stream_messages",
        json={"query": "test"},
    ):
        collected.append(event)

    assert len(collected) == 2
    assert collected[-1]["type"] == "error"


async def test_stream_error_status(mock_api, authenticated_client: EVEClient):
    mock_api.post("/conversations/c-1/stream_messages").mock(
        return_value=Response(401, json={"detail": "Unauthorized"})
    )

    with pytest.raises(APIError):
        async for _ in authenticated_client.stream(
            "/conversations/c-1/stream_messages",
            json={"query": "test"},
        ):
            pass


# --- Context manager ---


async def test_context_manager(base_url: str):
    async with EVEClient(base_url) as eve:
        assert eve._http is not None

    assert eve._http is None


async def test_close(base_url: str):
    eve = EVEClient(base_url)
    await eve._ensure_http_client()
    assert eve._http is not None

    await eve.close()
    assert eve._http is None
