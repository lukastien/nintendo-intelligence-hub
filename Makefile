.DEFAULT_GOAL := help

.PHONY: help install check test db-up db-down db-reset db-init ingest pipeline dbt-parse dbt-build app

help:
	@echo "install     Install the project and test tools"
	@echo "db-up       Start local PostgreSQL"
	@echo "db-init     Apply the schema, reference data, and synthetic sample"
	@echo "ingest      Download public sources and load parsed official rows"
	@echo "pipeline    Ingest, audit, build dbt marts, and record the run"
	@echo "check       Validate catalogs, grain rules, and the database when it is up"
	@echo "test        Run unit and integration tests"
	@echo "dbt-parse   Parse the dbt project"
	@echo "dbt-build   Build and test dbt views"
	@echo "app         Start the Streamlit shell"
	@echo "db-down     Stop PostgreSQL and keep the volume"
	@echo "db-reset    Stop PostgreSQL and delete the local volume"

install:
	python -m pip install -e ".[dev]"

check:
	nih check

test:
	pytest

db-up:
	docker compose up -d --wait

db-down:
	docker compose down

db-reset:
	docker compose down -v

db-init:
	nih init-db

ingest:
	nih ingest

pipeline:
	python -m nih pipeline run

dbt-parse:
	dbt parse --project-dir transformations/dbt --profiles-dir transformations/dbt

dbt-build:
	dbt build --project-dir transformations/dbt --profiles-dir transformations/dbt

app:
	streamlit run dashboards/app.py
