# --- Build Stage ---
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    python3-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .

# 1. Install standard requirements
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# 2. Download the SpaCy model explicitly into the prefix
# We use the prefix path to ensure it gets copied to the runner stage
RUN PATH="/install/bin:$PATH" PYTHONPATH="/install/lib/python3.11/site-packages" \
    pip install --no-cache-dir --prefix=/install \
    https://github.com/explosion/spacy-models/releases/download/en_core_web_md-3.8.0/en_core_web_md-3.8.0-py3-none-any.whl