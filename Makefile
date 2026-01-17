UV ?= uv

.PHONY: install dev test lint format

install:
	$(UV) sync

dev:
	$(UV) sync --extra dev

lint:
	$(UV) run black --check src tests
	$(UV) run isort --check src tests

format:
	$(UV) run black src tests
	$(UV) run isort src tests

test:
	$(UV) run pytest
