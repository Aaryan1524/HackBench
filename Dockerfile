# Production Dockerfile for HackBench Forensics Backend
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies (git for static repository analysis)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy project specification files
COPY pyproject.toml uv.lock ./

# Install python dependencies into virtualenv
RUN uv sync --frozen --no-install-project

# pyproject.toml declares README.md as the package readme, so the project build needs it (and the license).
COPY README.md LICENSE ./

# Copy application source code and historical dataset
COPY src/ ./src/
COPY data/ ./data/
COPY reports/ ./reports/

# Sync project installation
RUN uv sync --frozen

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
# Production: interactive API docs off.
# TRUST_PROXY_HEADERS stays off by default. Enable it only if your platform overwrites X-Forwarded-For with the
# real client address (the Next.js rewrite proxy does NOT, so a client could forge it).
ENV HACKBENCH_ENV=production

# Run as an unprivileged user; only the scratch/cache directories are writable.
RUN useradd --system --uid 10001 --no-create-home hackbench \
    && mkdir -p /app/data/raw/participant_repos /app/data/cache \
    && chown -R hackbench /app/data/raw/participant_repos /app/data/cache
USER hackbench

# Do not publish this port publicly: only the frontend should reach the backend.
EXPOSE 8000

# Health check (uses the port the platform assigns)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fs "http://localhost:${PORT:-8000}/health" || exit 1

# Start FastAPI via uvicorn on the platform-assigned $PORT (Railway, Render, Fly and Cloud Run all set it).
CMD ["sh", "-c", "exec uvicorn hackbench.api.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
