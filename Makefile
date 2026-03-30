PYTHON ?= python

.PHONY: install run lint format typecheck test migrate

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e .[dev]

run:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

lint:
	ruff check app tests

format:
	ruff check app tests --fix

typecheck:
	mypy app

test:
	pytest

migrate:
	alembic upgrade head