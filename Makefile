.PHONY: help setup test lint fmt e2e clean audit quality security

help:
	@echo "LP-PC Suite — Make targets"
	@echo "  setup     - Create venv + install deps"
	@echo "  test      - Run all tests"
	@echo "  test-cov  - Run with coverage"
	@echo "  lint      - Run ruff + mypy"
	@echo "  fmt       - Run black + ruff --fix"
	@echo "  e2e       - Run E2E with sample APK"
	@echo "  quality   - Code quality audit"
	@echo "  security  - Security audit"
	@echo "  audit     - Both audits"
	@echo "  clean     - Remove workspace caches"

setup:
	uv venv --python 3.11 --seed
	uv pip sync requirements.txt
	uv pip install pytest pytest-cov pytest-timeout pytest-qt

test:
	pytest src/tests -v

test-cov:
	pytest --cov=src --cov-report=term-missing --cov-report=html

lint:
	ruff check src
	mypy src --ignore-missing-imports

fmt:
	black src
	ruff check --fix src

e2e:
	python -u src/main.py sample.apk --mode "iap:dex,license:auto" --verbose

quality:
	python scripts/audit_quality.py

security:
	python scripts/audit_security.py

audit: quality security

clean:
	rm -rf workspace/cache workspace/decompiled
	rm -rf .pytest_cache .coverage htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} +