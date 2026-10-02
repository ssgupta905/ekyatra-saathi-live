.PHONY: help install demo test lint api console docker seed clean

PY ?= .venv/bin/python

help:
	@echo "make install   create .venv and install the backend (editable, with dev extras)"
	@echo "make demo      run the prototype on synthetic patients and score it"
	@echo "make test      run the test suite"
	@echo "make lint      ruff check + format check"
	@echo "make api       serve the FastAPI app on :8000"
	@echo "make console   run the navigator console on :5173 (proxies /api to :8000)"
	@echo "make docker    bring up postgres + neo4j for pilot-mode work"
	@echo "make seed      load the Neo4j dependency graph schema"

install:
	python3.12 -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev]"

demo:
	PYTHONPATH=backend $(PY) -m saathi.demo

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check backend tests
	$(PY) -m ruff format --check backend tests

api:
	PYTHONPATH=backend $(PY) -m uvicorn saathi.main:app --reload --port 8000

console:
	cd console && npm install && npm run dev

docker:
	docker compose up -d

seed:
	docker compose exec -T neo4j cypher-shell -u neo4j -p saathi-local \
		< backend/saathi/graph/schema.cypher

clean:
	rm -rf .venv console/node_modules console/dist .pytest_cache .ruff_cache saathi.db
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
