.PHONY: test lint format check

test:
	python -m pytest tests/ -v

lint:
	python -m ruff check src/ tests/

format:
	python -m ruff format src/ tests/

check: lint test
	@echo "All checks passed"
