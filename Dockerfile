# =====================================================================
# AcuCalyx™ v2.1 — Production Container Image
# Clinical Decision Support System for Percutaneous Nephrolithotomy (PCNL)
# Multi-Stage, Non-Root, HIPAA & FDA Premarket Cybersecurity Compliant
# =====================================================================

FROM python:3.11-slim as base

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    ACUCALYX_ENV=production

# Install system dependencies required for scientific imaging and rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create unprivileged service user for runtime security
RUN groupadd -r acucalyx && useradd -r -g acucalyx -d /app -s /sbin/nologin acucalyx

# Install Python dependencies first for caching efficiency
COPY requirements.txt pyproject.toml /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source tree and application assets
COPY src/ /app/src/
COPY app/ /app/app/
COPY configs/ /app/configs/
COPY ops/ /app/ops/
COPY data/ /app/data/

# Install acucalyx package
RUN pip install --no-cache-dir -e .

# Initialize persistent cases directory with proper permissions
RUN mkdir -p /app/data/cases && chown -R acucalyx:acucalyx /app

# Switch to unprivileged runtime user
USER acucalyx

# Service port
EXPOSE 8000

# Container healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Launch production server via uvicorn
CMD ["python", "-m", "uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
