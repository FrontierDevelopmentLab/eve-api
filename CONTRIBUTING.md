# Contributing to eve-api

Thank you for your interest in contributing! `eve-api` is a minimal
authenticated HTTP client for the EVE (Earth Virtual Expert) API. See
the [README](README.md) for what the project does and how to use it.

## Development setup

Follow the [Installation](README.md#installation) section of the
README, then install the pre-commit hooks:

```bash
poetry run pre-commit install
```

## Code quality

Pre-commit runs black, isort, autoflake, mypy, pylint, detect-secrets,
and pytest with coverage. Run the full suite locally before pushing:

```bash
poetry run pre-commit run --all-files
```

If a hook fails, fix the underlying issue rather than bypassing the
hook. If `detect-secrets` flags a false positive, update the baseline:

```bash
poetry run detect-secrets scan --baseline .secrets.baseline
```

## Testing

```bash
poetry run pytest
```

Tests use [`respx`](https://lundberg.github.io/respx/) to mock the EVE
API, so no live credentials are required. New behaviour should ship
with tests, and coverage is expected to stay at 100%.

## Pull requests

- Fork the repo and branch off `main`.
- Use a short branch prefix: `feat/`, `fix/`, `docs/`, or `chore/` etc.
- Keep each PR focused on one logical change.
- In the PR description, explain *what* changed and *why*, and link
  any related issue.
- Commit messages: imperative mood, focused on the *why*.
- Be ready to iterate on review feedback.

## Reporting issues

Open a [GitHub issue](https://github.com/FrontierDevelopmentLab/eve-api/issues)
with:

- steps to reproduce,
- expected vs actual behaviour,
- your environment (Python version, OS, relevant package versions).

## For maintainers

Maintainers can push branches directly to the repo; the same branch
naming, PR, and review expectations apply.
