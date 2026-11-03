# dbt reads these, so every $(DBT) command works from the repo root. Each tool
# loads .env itself: config.py, dbt and docker compose.
export DBT_PROJECT_DIR := malaysia_flights_dbt
export DBT_PROFILES_DIR := malaysia_flights_dbt

PYTHON := uv run python
DBT := uv run dbt
DBT_PACKAGES := $(DBT_PROJECT_DIR)/dbt_packages

.DEFAULT_GOAL := help
# docs is also a folder, so without .PHONY make would say it's up to date.
.PHONY: help install up down ingest backfill seeds transform test docs freshness

help: ## List the targets
	@grep -hE '^[a-z]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

install: ## Create the Python environment and install dependencies
	uv venv --python 3.13 --managed-python
	uv pip install -r requirements.txt -r requirements-dev.txt

up: ## Start Postgres in Docker
	docker compose up -d

down: ## Stop Postgres (the data is kept)
	docker compose down

ingest: ## Load one day: yesterday, or make ingest DATE=2026-09-15
	$(PYTHON) -m ingestion.main $(if $(DATE),--date $(DATE))

backfill: ## Load a range: make backfill START=2026-09-01 [END=2026-09-07], END defaults to yesterday
	$(if $(START),,$(error START is required, e.g. make backfill START=2026-09-01))
	$(PYTHON) -m ingestion.main --start $(START) $(if $(END),--end $(END))

seeds: ## Rebuild the three seed CSVs from their sources (needs Postgres running)
	$(PYTHON) -m scripts.build_airlines_seed
	$(PYTHON) -m scripts.build_airports_seed
	$(PYTHON) -m scripts.build_aircraft_seed

transform: | $(DBT_PACKAGES) ## Load the seeds, build every dbt model and run every test
	$(DBT) build

test: ## Run the Python tests
	$(PYTHON) -m pytest

docs: | $(DBT_PACKAGES) ## Generate and serve the dbt docs
	$(DBT) docs generate
	$(DBT) docs serve

freshness: | $(DBT_PACKAGES) ## Warn if the daily run has stopped
	$(DBT) source freshness

# Only runs when the folder is missing, e.g. on a fresh clone.
$(DBT_PACKAGES):
	$(DBT) deps
