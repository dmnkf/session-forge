UV ?= uv

.PHONY: install dev test lint format serve

install:
	$(UV) sync

dev:
	$(UV) sync --extra dev --extra server

lint:
	$(UV) run black --check src tests
	$(UV) run isort --check src tests

format:
	$(UV) run black src tests
	$(UV) run isort src tests

test:
	$(UV) run pytest

serve:
	$(UV) run uvicorn sf.server.app:app --host 127.0.0.1 --port 8765
