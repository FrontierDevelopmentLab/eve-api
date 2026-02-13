# eve-api

Minimal authenticated HTTP client for the EVE (Earth Virtual Expert) API.

Provides login, automatic JWT token refresh, and generic HTTP methods that return plain dicts. No domain-specific wrappers or Pydantic models.

## Installation

```bash
pip install -e ".[dev]"
```

## Usage

```python
from eve_api import EVEClient

async with EVEClient() as eve:
    await eve.login("user@example.com", "password")

    # Generic HTTP methods return parsed JSON (dict/list)
    me = await eve.get("/users/me")
    conv = await eve.post("/conversations", json={"name": "Test"})
    await eve.patch(f"/conversations/{conv['id']}", json={"name": "Renamed"})
    await eve.delete(f"/conversations/{conv['id']}")

    # Streaming (yields parsed SSE event dicts)
    async for event in eve.stream(
        f"/conversations/{conv_id}/stream_messages",
        json={"query": "What is Earth Observation?", "public_collections": ["eve-public"]},
    ):
        if event["type"] == "token":
            print(event["content"], end="")

    # Raw httpx.Response when needed
    response = await eve.request("GET", "/health", auth_required=False)

    # Direct token access
    print(eve.token)
    print(eve.auth_headers)
```

## Running tests

```bash
cd eve-api
pip install -e ".[dev]"
pytest
```
