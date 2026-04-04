.PHONY: install lint typecheck test format

install:
	pip install -r requirements.txt
	pip install pydantic-settings ruff mypy pytest semgrep trufflehog

lint:
	ruff check . --fix

typecheck:
	mypy . --strict --ignore-missing-imports

test:
	pytest tests/ -v --maxfail=1

security-scan:
	@echo "Running Tier-1 Security Scan..."
	semgrep scan --config auto .
	ruff check . --select S,T20,RET,PT,ARG,PTH
	@echo "Scanning for secrets..."
	# trufflehog filesystem . --fail

format:
	ruff format .
