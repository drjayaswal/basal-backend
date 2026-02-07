# --- Build Stage ---
FROM python:3.11-slim AS builder

# Build tools for psycopg2, bcrypt, and other C-extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    python3-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .

# Install to a prefix for easy migration to the runner stage
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Final Runner Stage ---
FROM python:3.11-slim AS runner

# libpq5 for Postgres, libgomp1 for ML models (scikit-learn/torch)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libgomp1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Hugging Face requires a user with UID 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR $HOME/app

# Copy installed libraries from builder to system path
COPY --from=builder /install /usr/local

# Copy application code and ensure the 'user' owns it
COPY --chown=user . .

# Pre-download SpaCy model (Essential for your reqs)
RUN python -m spacy download en_core_web_md

# Hugging Face strictly uses port 7860
EXPOSE 7860

# Port must be 7860 for HF Spaces
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]