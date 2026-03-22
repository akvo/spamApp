PYTHON ?= /opt/homebrew/Caskroom/miniconda/base/envs/geo/bin/python

.PHONY: test lint format check

test:
	$(PYTHON) -m pytest tests/ -v

lint:
	$(PYTHON) -m ruff check src/ tests/

format:
	$(PYTHON) -m ruff format src/ tests/

check: lint test
	@echo "All checks passed"
