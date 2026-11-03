# One image: the API. The web apps are static files and deploy separately
# (see frontend/apps); each reads its API address from a config.json beside it.

# ---- the service -------------------------------------------------------
FROM python:3.12-slim AS service

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies are declared in pyproject.toml. Install them from a stub build
# first so this layer caches: a change under backend/ then costs a wheel build,
# not a full dependency resolve.
COPY pyproject.toml README.md ./
COPY backend/ backend/
# The postgres extra: the records database is Postgres (Supabase) when deployed.
RUN pip install --no-cache-dir ".[postgres]"
# The committed reference cache. Without it every fact the tools need would be
# a live fetch on a cold start, and the first page load would hang on Nominatim.
COPY data/ data/

# Not root. Nothing here needs to write outside /tmp.
RUN useradd --create-home --uid 10001 saathi && chown -R saathi:saathi /app
USER saathi

EXPOSE 8000

# Render supplies $PORT; 8000 is the fallback for `docker run` locally.
# One worker on purpose: the world, the clock and the ledger are in-process
# state, so a second worker would serve a second, divergent reality.
CMD ["sh", "-c", "exec uvicorn saathi.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-graceful-shutdown 2"]
