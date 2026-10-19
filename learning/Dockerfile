# ==============================================================================
# Edukom Enterprise LMS - Multi-Stage Hardened Production Dockerfile
# Security:
# - Minimal attack surface (python:3.12-slim-bookworm)
# - Unprivileged non-root user (edukom UID/GID 10001)
# - No hardcoded secrets or build artifacts
# - Built-in health check probe
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Build Wheels & Dependencies
# ------------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /build/wheels -r requirements.txt


# ------------------------------------------------------------------------------
# Stage 2: Final Runtime Image
# ------------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS final

LABEL maintainer="Edukom IT & Infrastructure Team <support@edukom.ng>"
LABEL version="2.0-enterprise"
LABEL description="Edukom Group Proprietary Educational LMS"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    APP_HOME=/app

WORKDIR ${APP_HOME}

# Install minimal runtime libraries and utilities for health monitoring
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    netcat-openbsd \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

# Security: Create dedicated unprivileged non-root system group and user
RUN groupadd -g 10001 edukom && \
    useradd -u 10001 -g edukom -s /bin/bash -m -d /home/edukom edukom

# Copy pre-built wheels from builder stage
COPY --from=builder /build/wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# Create required runtime directories and set ownership
RUN mkdir -p ${APP_HOME}/public/Assets ${APP_HOME}/media ${APP_HOME}/logs && \
    chown -R edukom:edukom ${APP_HOME} /home/edukom

# Copy application source code
COPY --chown=edukom:edukom . ${APP_HOME}

# Make entrypoint script executable
RUN chmod +x ${APP_HOME}/docker-entrypoint.sh

# Drop privileges to non-root user
USER edukom

EXPOSE 8000

# Docker Healthcheck targeting the lightweight /healthz endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/healthz/ || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
