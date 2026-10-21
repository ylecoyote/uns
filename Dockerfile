# UNS multi-stage container build using uv.
#
# Build:
#   docker build -t uns:dev .
#
# Run UNS (HTTP API; serve the built console on the same origin):
#   docker run --rm -p 127.0.0.1:8000:8000 \
#     -e AGSIGNAL_API_KEY=<secret> \
#     -e AGSIGNAL_API_PRINCIPAL=ops-rotation \
#     -e DATABASE_URL=postgresql+psycopg2://... \
#     -e AGSIGNAL_REDIS_URL=redis://... \
#     uns:dev
#
# Production:
#   - Front with a reverse proxy that terminates TLS and restricts /metrics,
#     /healthz, /readyz to the internal scrape network.
#   - See docs/DEPLOYMENT.md for the full hardening recipe.

ARG PYTHON_VERSION=3.12

# ---------------------------------------------------------------------------
# Stage 1: builder — produce the wheel with uv
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

# Install uv (fast Python package manager, used to build the wheel).
COPY --from=ghcr.io/astral-sh/uv:0.4 /uv /uvx /usr/local/bin/

WORKDIR /build

# Copy only what the wheel build actually needs.
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src/ ./src/

RUN uv build --wheel

# ---------------------------------------------------------------------------
# Stage 2: runtime — minimal image with the wheel installed
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

# libpq is needed at runtime by psycopg2-binary.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user (uid 1001 to avoid clashing with common host uids).
RUN groupadd --system --gid 1001 agsignal \
    && useradd --system --uid 1001 --gid agsignal \
        --create-home --home-dir /home/agsignal --shell /sbin/nologin agsignal

# Install AGSignal from the built wheel with the [full] meta-extra so all
# runtime surfaces (HTTP server, Redis, SQL, MCP, channel adapters) are
# available, plus the Postgres driver. Derivative images that only need a
# subset (e.g. SDK-only producers) can install with no extras instead.
COPY --from=builder /build/dist/ /tmp/dist/
RUN set -- /tmp/dist/uns-*.whl \
    && pip install --no-cache-dir "$1[full]" \
        "psycopg2-binary>=2.9.0" \
    && rm -rf /tmp/dist

USER agsignal
WORKDIR /home/agsignal

# Container-friendly defaults:
#   - bind to 0.0.0.0 (the operator's reverse proxy is the boundary; native
#     installs default to 127.0.0.1 per docs/DEPLOYMENT.md).
#   - unbuffered stdout/stderr so logs are streamed, not batched.
ENV AGSIGNAL_HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# Container-internal liveness probe. Compose / k8s should still hit /readyz
# externally — this is just for `docker run --health` users.
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)" \
        || exit 1

# Unified AGSignal HTTP service. Both Core (write) and Console (read)
# surfaces live in one process post-Phase-3.
CMD ["uvicorn", "uns.app:app", "--host", "0.0.0.0", "--port", "8000"]
