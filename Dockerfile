# --- Stage 1: Build & Security Scanning ---
FROM python:3.10-slim-bullseye AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies into a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt

# --- Stage 2: Hardened Runtime Environment ---
FROM python:3.10-slim-bullseye

# Zero-Trust: Mandatory non-root user for SOC2 compliance
RUN groupadd -g 10001 nexus && \
    useradd -u 10001 -g nexus -s /bin/bash -m nexus

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy virtualenv from builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy only necessary files
COPY api/ api/
COPY core/ core/
COPY scripts/ scripts/
COPY app.py .
COPY pyproject.toml .

# Set secure permissions
RUN chown -R nexus:nexus /app && \
    chmod -R 550 /app && \
    chmod -R 770 /app/scripts

# Switch to non-root user
USER nexus

# Tier-1 Health Check: Direct integration with our deep health probe
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# Entrypoint for high-concurrency production (FastAPI)
# Note: Streamlit was the legacy entrypoint; moving to Uvicorn for Tier-1 API performance.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--proxy-headers", "--forwarded-allow-ips", "*"]
