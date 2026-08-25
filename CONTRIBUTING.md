# Contributing

Keep contributions focused, consistent, and easy to integrate.

## Branching

main
 └─ feature/<short-description>

Keep `main` stable and deployable.

## Pull Requests

Every change should go through a PR.

Before submitting a PR:

- [ ] `uv run ruff check .` passes
- [ ] `uv run python -m pytest` passes
- [ ] New rules go into `policies/*.yaml`, not hardcoded conditionals
- [ ] New failure paths fail closed
- [ ] If you change a contract in `domain/models.py`, check its downstream consumers
- [ ] No secrets or local/generated files are committed
- [ ] Changes are limited to the intended task

## Local Setup

Install dependencies:

    uv sync

Create a local environment file:

    cp .env.example .env

Run the application:

    uv run uvicorn apps.api.main:app --reload

API docs:

    http://localhost:8000/docs

Or with Docker:

    docker compose up --build

## Development

Run tests:

    uv run python -m pytest

Run linting:

    uv run ruff check .

Keep business logic testable without requiring live external services.

Follow the existing architecture, contracts, and engineering rules. Avoid unrelated changes or unnecessary dependencies.