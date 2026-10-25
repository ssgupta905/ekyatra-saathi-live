# One image, one service: the console apps and the API on one origin.
#
# Not two services. The recording stage loads the family and hospital apps into
# iframes by origin, so splitting them across hosts would put a cross-origin
# boundary through the middle of the demo and buy nothing.

# ---- build the console -------------------------------------------------
FROM node:22-slim AS console

WORKDIR /frontend
# Dependencies first: this layer is cached unless a manifest or the lockfile
# moves, which turns a typical rebuild from two minutes into fifteen seconds.
# `npm ci` in a workspace needs every workspace's package.json present.
COPY frontend/package.json frontend/package-lock.json ./
COPY frontend/packages/api-client/package.json packages/api-client/
COPY frontend/packages/i18n/package.json packages/i18n/
COPY frontend/packages/theme/package.json packages/theme/
COPY frontend/packages/ui-web/package.json packages/ui-web/
COPY frontend/apps/console/package.json apps/console/
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build -w ekyatra-saathi-console

# ---- the service -------------------------------------------------------
FROM python:3.12-slim AS service

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    SAATHI_CONSOLE_DIST=/app/console/dist

WORKDIR /app

# Dependencies are declared in pyproject.toml. Install them from a stub build
# first so this layer caches: a change under backend/ then costs a wheel build,
# not a full dependency resolve.
COPY pyproject.toml README.md ./
COPY backend/ backend/
RUN pip install --no-cache-dir .
# The committed reference cache. Without it every fact the tools need would be
# a live fetch on a cold start, and the first page load would hang on Nominatim.
COPY data/ data/
COPY --from=console /frontend/apps/console/dist/ console/dist/

# Not root. Nothing here needs to write outside /tmp.
RUN useradd --create-home --uid 10001 saathi && chown -R saathi:saathi /app
USER saathi

EXPOSE 8000

# Render supplies $PORT; 8000 is the fallback for `docker run` locally.
# One worker on purpose: the world, the clock and the ledger are in-process
# state, so a second worker would serve a second, divergent reality.
CMD ["sh", "-c", "exec uvicorn saathi.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-graceful-shutdown 2"]
