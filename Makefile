.PHONY: help install install-dev test lint fmt backtest scan serve docker clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

install:  ## Install runtime dependencies
	pip install -r requirements.txt && pip install -e .

install-dev:  ## Install dev + web + data extras
	pip install -e ".[dev,web,data,security]"

test:  ## Run the test suite
	pytest

lint:  ## Lint with ruff
	ruff check quanttrade tests

fmt:  ## Auto-format with ruff
	ruff check --fix quanttrade tests

backtest:  ## Run a demo backtest
	python -m quanttrade.cli backtest --strategy ma_crossover --symbols AAPL,MSFT

scan:  ## Run the market scanner on a demo universe
	python -m quanttrade.cli scan --symbols AAPL,MSFT,TSLA,NVDA,SPY

serve:  ## Run the FastAPI server
	uvicorn quanttrade.api.app:app --reload

docker:  ## Build and run the full stack
	docker compose up --build

clean:  ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
