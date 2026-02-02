# --- Build Stage ---
FROM python:3.11-slim AS builder

# Install build dependencies for database drivers
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .

# Install to a local path to keep the runner stage clean
RUN pip install --no-cache-dir --user -r requirements.txt

# --- Final Stage ---
FROM python:3.11-slim AS runner

# Install the runtime library for Postgres
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the installed packages from the builder
COPY --from=builder /root/.local /root/.local
# Copy your app code
COPY . .

# Ensure the app can find the installed packages
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Use Render's default port 10000
EXPOSE 10000

# Dynamic port binding for Render
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]