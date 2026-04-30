"""Tests for the EVEClient."""

import json
from http import HTTPStatus
from typing import Literal, TypedDict

import pytest
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


class StatusEvent(TypedDict):
    """SSE event emitted while the server is still working."""

    type: Literal["status"]
    content: str


class TokenEvent(TypedDict):
    """SSE event carrying an incremental token of the streamed response."""

    type: Literal["token"]
    content: str


class FinalEvent(TypedDict):
    """SSE event marking the final, complete response."""

    type: Literal["final"]
    content: str
    message_id: str


class ErrorEvent(TypedDict):
    """SSE event indicating the stream terminated with an error."""

    type: Literal["error"]
    content: str


SSEEvent = StatusEvent | TokenEvent | FinalEvent | ErrorEvent

# --- Authentication ---


async def test_login_success(mock_api, client: EVEClient):
    """Test login success"""
    tok = "tok-123"
    mock_api.post("/login").mock(
        return_value=Response(
            HTTPStatus.OK,
            json={
                "access_token": tok,
                "refresh_token": "ref-456",
            },
        )
    )

    await client.login("user@example.com", "password")

    assert client.is_authenticated()
    assert client.token == tok
    assert client.auth_headers == {"Authorization": f"Bearer {tok}"}


async def test_login_invalid_credentials(mock_api, client: EVEClient):
    """Test login for invalid credentials raises AuthenticationError"""
    mock_api.post("/login").mock(
        return_value=Response(
            HTTPStatus.UNAUTHORIZED,
            json={
                "detail": "Invalid credentials",
            },
        )
    )

    with pytest.raises(AuthenticationError, match="Invalid email or password"):
        await client.login("bad@example.com", "wrong")

    assert not client.is_authenticated()


async def test_login_account_not_activated(mock_api, client: EVEClient):
    """Test login for non-activated account raises AuthenticationError"""
    mock_api.post("/login").mock(
        return_value=Response(
            HTTPStatus.FORBIDDEN,
            json={
                "detail": "Account not activated",
            },
        )
    )

    with pytest.raises(AuthenticationError, match="Account not activated"):
        await client.login("user@example.com", "password")


async def test_not_authenticated_error(client: EVEClient):
    """Test that before login NotAuthenticatedError is raised"""
    with pytest.raises(NotAuthenticatedError):
        await client.get("/users/me")


async def test_token_property_none_before_login(client: EVEClient):
    """Test that the token attribute before login is None"""
    assert client.token is None


# --- GET ---


async def test_get(mock_api, authenticated_client: EVEClient):
    """Test GET"""
    user_id = "user-1"
    user_email = "test@example.com"
    mock_api.get("/users/me").mock(
        return_value=Response(
            HTTPStatus.OK,
            json={
                "id": user_id,
                "email": user_email,
            },
        )
    )

    data = await authenticated_client.get("/users/me")

    assert data["id"] == user_id
    assert data["email"] == user_email


async def test_get_with_params(mock_api, authenticated_client: EVEClient):
    """Test GET with params"""
    data_name = "Public"
    mock_api.get("/collections/public").mock(
        return_value=Response(
            HTTPStatus.OK,
            json={
                "data": [{"id": "c-1", "name": data_name}],
                "meta": {"total_count": 1},
            },
        )
    )

    data = await authenticated_client.get(
        "/collections/public", params={"page": 1}
    )

    assert len(data["data"]) == 1
    assert data["data"][0]["name"] == data_name


# --- POST ---


async def test_post(mock_api, authenticated_client: EVEClient):
    """Test POST"""
    chat_id = "conv-1"
    chat_name = "New Chat"
    mock_api.post("/conversations").mock(
        return_value=Response(
            HTTPStatus.CREATED,
            json={
                "id": chat_id,
                "name": "New Chat",
            },
        )
    )

    data = await authenticated_client.post(
        "/conversations", json={"name": chat_name}
    )

    assert data["id"] == chat_id
    assert data["name"] == chat_name


# --- PATCH ---


async def test_patch(mock_api, authenticated_client: EVEClient):
    """Test PATCH"""
    new_name = "Renamed"
    mock_api.patch("/conversations/conv-1").mock(
        return_value=Response(
            HTTPStatus.OK,
            json={
                "id": "conv-1",
                "name": new_name,
            },
        )
    )

    data = await authenticated_client.patch(
        "/conversations/conv-1", json={"name": new_name}
    )

    assert data["name"] == new_name


# --- DELETE ---


async def test_delete(mock_api, authenticated_client: EVEClient):
    """Test deleting a conversation works when a response body is not included"""
    mock_api.delete("/conversations/conv-1").mock(
        return_value=Response(HTTPStatus.NO_CONTENT)
    )

    result = await authenticated_client.delete("/conversations/conv-1")

    assert result is None


async def test_delete_with_body(mock_api, authenticated_client: EVEClient):
    """Test deleting a conversation works when including a response body"""
    mock_api.delete("/conversations/conv-1").mock(
        return_value=Response(
            HTTPStatus.OK,
            json={
                "deleted": True,
            },
        )
    )

    result = await authenticated_client.delete("/conversations/conv-1")

    assert result["deleted"] is True


# --- request() with auth_required=False ---


async def test_request_no_auth(mock_api, client: EVEClient):
    """Test EVEClient when auth_required=False"""
    status = "ok"
    mock_api.get("/health").mock(
        return_value=Response(HTTPStatus.OK, json={"status": status})
    )

    response = await client.request("GET", "/health", auth_required=False)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["status"] == status


# --- Error handling ---


async def test_404_raises_not_found(mock_api, authenticated_client: EVEClient):
    """Test that 404 response code raises NotFoundError"""
    mock_api.get("/conversations/missing").mock(
        return_value=Response(
            HTTPStatus.NOT_FOUND,
            json={
                "detail": "Not found",
            },
        )
    )

    with pytest.raises(NotFoundError, match="Not found") as exc_info:
        await authenticated_client.get("/conversations/missing")

    assert exc_info.value.status_code == HTTPStatus.NOT_FOUND


async def test_403_raises_forbidden(mock_api, authenticated_client: EVEClient):
    """Test that 403 response code raises ForbiddenError"""
    mock_api.get("/admin/users").mock(
        return_value=Response(
            HTTPStatus.FORBIDDEN,
            json={
                "detail": "Forbidden",
            },
        )
    )

    with pytest.raises(ForbiddenError) as exc_info:
        await authenticated_client.get("/admin/users")

    assert exc_info.value.status_code == HTTPStatus.FORBIDDEN


async def test_400_raises_validation_error(
    mock_api, authenticated_client: EVEClient
):
    """Test that 400 response code raises ValidationError"""
    mock_api.post("/conversations").mock(
        return_value=Response(
            HTTPStatus.BAD_REQUEST,
            json={
                "detail": "name is required",
            },
        )
    )

    with pytest.raises(ValidationError, match="name is required") as exc_info:
        await authenticated_client.post("/conversations", json={})

    assert exc_info.value.status_code == HTTPStatus.BAD_REQUEST


async def test_500_raises_server_error(
    mock_api, authenticated_client: EVEClient
):
    """Test that 500 response code raises ServerError"""
    mock_api.get("/broken").mock(
        return_value=Response(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            json={
                "detail": "Internal server error",
            },
        )
    )

    with pytest.raises(ServerError) as exc_info:
        await authenticated_client.get("/broken")

    assert exc_info.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


async def test_422_raises_api_error(mock_api, authenticated_client: EVEClient):
    """Test that 422 response code raises APIError"""
    unprocessable_entity = 422
    mock_api.post("/conversations").mock(
        return_value=Response(
            unprocessable_entity,
            json={
                "detail": [{"msg": "field required", "type": "missing"}],
            },
        )
    )

    with pytest.raises(APIError) as exc_info:
        await authenticated_client.post("/conversations", json={})

    assert exc_info.value.status_code == unprocessable_entity


async def test_response_missing_detail_raises_api_error(
    mock_api, authenticated_client: EVEClient
):
    """Test that error response without 'detail' key raises APIError"""
    unknown_error = 452
    mock_api.post("/conversations").mock(
        return_value=Response(
            unknown_error,
            json="Some invalid JSON",
        )
    )

    with pytest.raises(APIError) as exc_info:
        await authenticated_client.post("/conversations", json={})

    assert exc_info.value.status_code == unknown_error


# --- Streaming ---


def _sse_response(*events: SSEEvent, done: bool = True) -> Response:
    """Build a Response whose body is SSE-formatted lines."""
    lines = []
    for event in events:
        lines.append(f"data: {json.dumps(event)}\n\n")
    if done:
        lines.append("data: [DONE]\n\n")
    body = "".join(lines)
    return Response(
        HTTPStatus.OK,
        content=body.encode(),
        headers={"content-type": "text/event-stream"},
    )


async def test_stream(mock_api, authenticated_client: EVEClient):
    """Test streaming"""
    status_text = "status"
    final_text = "final"
    events: list[SSEEvent] = [
        StatusEvent(type="status", content="Searching..."),
        TokenEvent(type="token", content="Hello"),
        TokenEvent(type="token", content=" world"),
        FinalEvent(type="final", content="Hello world", message_id="m-1"),
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
    assert len(collected) == len(events)
    assert collected[0]["type"] == status_text
    assert collected[-1]["type"] == final_text


async def test_stream_stops_on_error_event(
    mock_api, authenticated_client: EVEClient
):
    """Test that streaming stops on an error event"""
    error_text = "error"
    events: list[SSEEvent] = [
        TokenEvent(type="token", content="partial"),
        ErrorEvent(type="error", content="Something went wrong"),
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

    assert len(collected) == len(events)
    assert collected[-1]["type"] == error_text


async def test_stream_error_status(mock_api, authenticated_client: EVEClient):
    """Test status from stream error"""
    mock_api.post("/conversations/c-1/stream_messages").mock(
        return_value=Response(
            HTTPStatus.UNAUTHORIZED, json={"detail": "Unauthorized"}
        )
    )

    with pytest.raises(APIError):
        async for _ in authenticated_client.stream(
            "/conversations/c-1/stream_messages",
            json={"query": "test"},
        ):
            pass


async def test_stream_done_no_error(mock_api, authenticated_client: EVEClient):
    """Test streaming when it returns data: [DONE] with no errors"""
    events: list[SSEEvent] = [
        TokenEvent(type="token", content="Hello"),
        TokenEvent(type="token", content=" world"),
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

    # Should stop even if no "final" event
    assert len(collected) == len(events)


async def test_stream_error_invalid_json(
    mock_api, authenticated_client: EVEClient
):
    """Test status from stream error"""
    events: list[SSEEvent] = [
        TokenEvent(type="token", content="Hello"),
        TokenEvent(type="token", content=" world"),
    ]
    lines = []
    for event in events:
        lines.append(f"data: {json.dumps(event)}\n\n")
    lines.append("data: Some invalid JSON")
    body = "".join(lines)
    response = Response(
        HTTPStatus.OK,
        content=body.encode(),
        headers={"content-type": "text/event-stream"},
    )
    mock_api.post("/conversations/c-1/stream_messages").mock(
        return_value=response
    )

    with pytest.raises(StreamError):
        async for _ in authenticated_client.stream(
            "/conversations/c-1/stream_messages",
            json={"query": "test"},
        ):
            pass


# --- Context manager ---


async def test_context_manager(base_url: str):
    """Test the EVEClient as a context manager"""
    async with EVEClient(base_url) as eve:
        assert eve._http is not None  # pylint:disable=protected-access

    assert eve._http is None  # pylint:disable=protected-access


async def test_close(base_url: str):
    """Test closing the EVEClient"""
    eve = EVEClient(base_url)
    await eve._ensure_http_client()  # pylint:disable=protected-access
    assert eve._http is not None  # pylint:disable=protected-access

    await eve.close()
    assert eve._http is None  # pylint:disable=protected-access
