# Vektia - Multi-stage Docker Build
FROM python:3.11-slim AS base

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# --- API Server ---
FROM base AS api
EXPOSE 8000
CMD ["uvicorn", "vektia.main:app", "--host", "0.0.0.0", "--port", "8000"]

# --- Background ML Worker ---
FROM base AS worker
CMD ["python", "-m", "vektia.worker.ml_worker"]
