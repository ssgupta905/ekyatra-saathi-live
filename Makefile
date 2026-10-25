.PHONY: help install demo demo-audio demo-mov demo-video demo-video-headless fetch-reference test lint api console web-test web-typecheck emulator android-build android-test android-install android-run android-strings docker seed clean

PY ?= .venv/bin/python
# Override when something else already owns 8000:  make api PORT=8001
PORT ?= 8000

# The Android app is a standard Gradle project (android/). It needs JDK 17 and
# the Android SDK that ships with Android Studio; the emulator is whichever AVD
# is installed.
AVD ?= Pixel_3a_API_33_arm64-v8a
ANDROID_SDK ?= $(HOME)/Library/Android/sdk
ADB = $(ANDROID_SDK)/platform-tools/adb
GRADLE = cd android && JAVA_HOME=$$(/usr/libexec/java_home -v 17) ./gradlew
APK = android/app/build/outputs/apk/debug/app-debug.apk

help:
	@echo "make install   create .venv and install the backend (editable, with dev extras)"
	@echo "make demo      run the prototype on synthetic patients and score it"
	@echo "make fetch-reference  fill the geo cache from real services (needs network)"
	@echo "make test      run the test suite"
	@echo "make lint      ruff check + format check"
	@echo "make api       serve the FastAPI app on :8000 (override with PORT=8001)"
	@echo "make console   run the navigator console on :5173 (proxies /api to :8000)"
	@echo "make web-test   frontend unit tests (api client, i18n, theme)"
	@echo "make web-typecheck   strict TypeScript across every frontend package and app"
	@echo "make demo-video  drive the console in a visible browser and record it"
	@echo "make demo-video-headless   the same run with no window"
	@echo "make demo-mov    convert the newest recording to .mov in ~/Documents"
	@echo "make emulator   boot the Android emulator (AVD=$(AVD))"
	@echo "make android-run   build the family app, install it on the running emulator and open it"
	@echo "make android-test  the family app's unit tests"
	@echo "make android-strings   regenerate the app's words and colours from the shared web sources"
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
	cd frontend && npm install --no-audit --no-fund && npm run dev -w ekyatra-saathi-console

web-test:
	cd frontend && npm test

web-typecheck:
	cd frontend && npm run typecheck

# Boots in the foreground of its own window; leave it running and use the
# android-* targets from another terminal.
emulator:
	$(ANDROID_SDK)/emulator/emulator -avd $(AVD) -no-snapshot-load

android-build:
	$(GRADLE) :app:assembleDebug

android-test:
	$(GRADLE) :app:testDebugUnitTest

android-install: android-build
	$(ADB) install -r $(APK)

# The emulator reaches this Mac's API at 10.0.2.2:8000, so `make api` must be running.
android-run: android-install
	$(ADB) shell am start -n org.ekyatra.saathi/.MainActivity

# Node 22+: the generator reads the TypeScript i18n source directly.
android-strings:
	PATH=/opt/homebrew/opt/node@22/bin:$$PATH node android/tools/generate.mjs

# Convert the newest recording to a QuickTime .mov in ~/Documents.
# Playwright only writes WebM/VP8, which nothing on a stock Mac decodes —
# QuickTime, Preview and avconvert all refuse it, and renaming the file to
# .mp4 hides that rather than fixing it. See demo/to-mov.mjs.
demo-mov:
	cd demo && node to-mov.mjs "$$(ls -t ../recordings/*.webm | head -1)" $(DEST)

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
	rm -rf android/.gradle android/build android/app/build .venv frontend/node_modules frontend/apps/*/dist .pytest_cache .ruff_cache saathi.db
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
