PYTHON ?= python

.PHONY: install run lint format typecheck test migrate backtest

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

backtest:
	$(PYTHON) -m app.main backtest --strategy $(STRATEGY) --route-id $(ROUTE_ID) --pair $(PAIR) --start-ts $(START_TS) --end-ts $(END_TS) $(if $(PARAMETER_SET_ID),--parameter-set-id $(PARAMETER_SET_ID),)
