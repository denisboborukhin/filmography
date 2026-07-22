.PHONY: install check test build web-build web-test python-test

install:
	npm ci
	uv sync --dev

check:
	npm run check
	npm run lint
	uv run ruff check python tests
	uv run ruff format --check python tests/python
	uv run pyright

test: web-test python-test

web-test:
	npm test -- --run

python-test:
	uv run pytest

web-build:
	npm run build

build: check test web-build
