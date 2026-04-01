.PHONY: install lint typecheck test format

install:
	pip install -r requirements.txt
	pip install pydantic-settings ruff mypy pytest

lint:
	ruff check .

typecheck:
	mypy .

test:
	pytest tests/

format:
	ruff format .
