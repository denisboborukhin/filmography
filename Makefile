.PHONY: install check test build web-build web-test python-test

install:
	npm install
	uv sync --dev

check:
	npm run check
	uv run ruff check python tests
	uv run pyright python

test: web-test python-test

web-test:
	npm test -- --run

python-test:
	uv run pytest

web-build:
	npm run build

build: check test web-build
