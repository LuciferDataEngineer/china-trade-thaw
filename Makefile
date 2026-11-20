PY := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)
export PYTHONPATH := src
export MPLBACKEND := Agg

.PHONY: snapshot pipeline lint test lake e2e up down

snapshot:
	$(PY) -m china_trade.snapshot

pipeline:
	$(PY) -m china_trade.build

lint:
	$(PY) -m ruff check src tests
	$(PY) -m ruff format --check src tests

test:
	$(PY) -m pytest -m "not lake and not e2e"

lake:
	$(PY) -m pytest -m lake

e2e:
	$(PY) -m pytest -m e2e

up:
	docker compose up -d postgres rustfs

down:
	docker compose down
