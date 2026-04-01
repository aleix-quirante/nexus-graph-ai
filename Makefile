.PHONY: install lint typecheck test all

install:
	pip install -e ".[dev]"

lint:
	ruff check .

typecheck:
	mypy .

test:
	pytest tests/

all: lint typecheck test
