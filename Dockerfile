# --- QuantTrade API/engine image -----------------------------------------
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps (build tools for scientific wheels if needed).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (better layer caching).
COPY requirements.txt pyproject.toml ./
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install "fastapi>=0.110" "uvicorn[standard]>=0.27" pydantic>=2 yfinance cryptography

# Copy source and install the package.
COPY quanttrade ./quanttrade
COPY config ./config
RUN pip install -e .

# Non-root user.
RUN useradd -m quant && chown -R quant:quant /app
USER quant

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:8000/api/health'); sys.exit(0)" || exit 1

CMD ["uvicorn", "quanttrade.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
