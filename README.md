# eve-api

[![CI](https://github.com/FrontierDevelopmentLab/eve-api/actions/workflows/main.yml/badge.svg)](https://github.com/FrontierDevelopmentLab/eve-api/actions/workflows/main.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)](https://github.com/FrontierDevelopmentLab/eve-api)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

EVE-API is a minimal authenticated HTTP client for EVE (Earth Virtual Expert).
It provides login, automatic JWT token refresh, and generic HTTP methods that return plain dicts. There are no domain-specific wrappers or Pydantic models.


EVE-API is part of an initiative by [Trillium Technologies](https://trillium.tech/) and ESA to
realize the vision of Earth system predictability (ESP).
You can read about the ESP vision [here](https://eslab.ai/esp).


## Installation

For the development version:
```bash
poetry install
```
or
```bash
pip install -e ".[dev]"
```

Supported Python versions: 3.11–3.14.

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

## Configuration

`EVEClient` is configured via constructor arguments — no environment
variables are read.

| Argument | Default | Purpose |
| --- | --- | --- |
| `base_url` | `https://api.eve-chat.chat` | Base URL of the EVE API. |
| `timeout` | `30.0` | Default request timeout in seconds. Per-call timeouts can be passed to individual methods. |

## Authentication

`login()` exchanges email/password for a JWT access token and a
refresh token. Tokens are held in memory on the client instance.

Before every authenticated request, the client refreshes the access
token if it is within 5 minutes of expiry (default expiry: 1 hour);
refresh is lazy, not background. If the refresh token itself has
expired, `TokenExpiredError` is raised and the caller must call
`login()` again.

For unauthenticated endpoints, pass `auth_required=False` to
`request()`.

## Examples

See [`examples/quickstart.py`](examples/quickstart.py) for a runnable
script and [`examples/tutorial.ipynb`](examples/tutorial.ipynb) for a
notebook walk-through.

## Errors

All errors derive from `EVEError`. Common subclasses exported from
`eve_api`: `AuthenticationError`, `NotAuthenticatedError`,
`TokenExpiredError`, `APIError`, `NotFoundError`, `ForbiddenError`,
`ValidationError`, `ServerError`, `StreamError`.

## Running tests

```bash
pytest
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup,
pre-commit hooks, and PR conventions.

## Acknowledgements

Originally created by the GeoSTARS (STARS: Scientific Testing of Agentic Reasoning) team:
([Raúl Ramos](https://github.com/rramosp), [James Walsh](https://github.com/dead-water),
[Will Fawcett](https://github.com/will-fawcett), and [Russell Spiewak](https://github.com/r-spiewak)).
Supported by the ESA Phi-Lab as part of Trillium Technologies Earth Systems Lab [ESL](https://eslab.ai/).


## License

MIT licensed. See [LICENSE](LICENSE) for the full text.

## Copyright

© 2026 Trillium Technologies Ltd.
