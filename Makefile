.PHONY: help install demo demo-audio demo-video demo-video-headless fetch-reference test lint api console docker seed clean

PY ?= .venv/bin/python
# Override when something else already owns 8000:  make api PORT=8001
PORT ?= 8000

help:
	@echo "make install   create .venv and install the backend (editable, with dev extras)"
	@echo "make demo      run the prototype on synthetic patients and score it"
	@echo "make fetch-reference  fill the geo cache from real services (needs network)"
	@echo "make test      run the test suite"
	@echo "make lint      ruff check + format check"
	@echo "make api       serve the FastAPI app on :8000 (override with PORT=8001)"
	@echo "make console   run the navigator console on :5173 (proxies /api to :8000)"
	@echo "make demo-video  drive the console in a visible browser and record it"
	@echo "make demo-video-headless   the same run with no window"
	@echo "make docker    bring up postgres + neo4j for pilot-mode work"
	@echo "make seed      load the Neo4j dependency graph schema"

install:
	python3.12 -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev]"

demo:
	PYTHONPATH=backend $(PY) -m saathi.demo

fetch-reference:
	PYTHONPATH=backend $(PY) -m saathi.tools.fetch

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check backend tests
	$(PY) -m ruff format --check backend tests

api:
# --timeout-graceful-shutdown is not optional here. `/api/stream` is an
# endless SSE generator, so a browser tab holding one open makes uvicorn's
# graceful shutdown wait forever: every --reload hangs at "waiting for
# connections to close" and the port stays held by a dead server.
	PYTHONPATH=backend $(PY) -m uvicorn saathi.main:app --reload --port $(PORT) \
		--timeout-graceful-shutdown 2

console:
	cd console && npm install && npm run dev

# The spoken question the recorded demo plays into Chrome's fake microphone.
# Synthesised rather than recorded, because it is an *input* — the stand-in for
# a caregiver speaking. Everything downstream of it is real: a real
# MediaRecorder captures it and real Groq Whisper transcribes it.
# macOS only (`say`/`afconvert`); the file is committed so this rarely runs.
demo-audio:
	@mkdir -p demo/audio
	say -v Lekha -o /tmp/saathi-q.aiff "दवा का क्या होगा अगर हम नहीं आ पाए"
	afconvert -f WAVE -d LEI16@48000 -c 1 /tmp/saathi-q.aiff demo/audio/hi-dose-question.wav
	@rm -f /tmp/saathi-q.aiff
	@echo "wrote demo/audio/hi-dose-question.wav"

# Watch it happen in a real browser window, and record it.
demo-video:
	cd demo && npm install --no-audit --no-fund && npx playwright install chromium \
		&& SAATHI_API_URL=http://localhost:$(PORT) node autodemo.mjs

# Same run with no window, for CI or over SSH.
demo-video-headless:
	cd demo && npm install --no-audit --no-fund && npx playwright install chromium \
		&& SAATHI_DEMO_HEADLESS=true SAATHI_API_URL=http://localhost:$(PORT) node autodemo.mjs

docker:
	docker compose up -d

seed:
	docker compose exec -T neo4j cypher-shell -u neo4j -p saathi-local \
		< backend/saathi/graph/schema.cypher

clean:
	rm -rf .venv console/node_modules console/dist .pytest_cache .ruff_cache saathi.db
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
