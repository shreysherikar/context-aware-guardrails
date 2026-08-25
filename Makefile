.PHONY: venv install run test lint format typecheck ci clean

venv:
	python3 -m venv .venv

install:
	. .venv/bin/activate && pip install --upgrade pip && pip install -e ".[dev]"

run:
	. .venv/bin/activate && uvicorn apps.api.main:app --reload --port 8000

test:
	. .venv/bin/activate && pytest -v

lint:
	. .venv/bin/activate && ruff check .

format:
	. .venv/bin/activate && ruff format .

typecheck:
	. .venv/bin/activate && mypy .

ci: lint typecheck test

clean:
	rm -rf .venv audit.db **/__pycache__ .pytest_cache .mypy_cache .ruff_cache
