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

# Copy application source code and historical dataset
COPY src/ ./src/
COPY data/ ./data/
COPY reports/ ./reports/

# Sync project installation
RUN uv sync --frozen

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Start FastAPI server via uvicorn
CMD ["uvicorn", "hackbench.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
