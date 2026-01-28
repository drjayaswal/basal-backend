# --- Build Stage ---
FROM python:3.11-alpine AS builder

# Alpine needs these to build psycopg2 from source
RUN apk add --no-cache gcc musl-dev postgresql-dev

WORKDIR /app
COPY requirements.txt .

# Use psycopg2-binary in requirements.txt or install it here
RUN pip install --no-cache-dir --prefix=/install psycopg2-binary
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Final Stage ---
FROM python:3.11-alpine AS runner

WORKDIR /app

# Copy the libraries from the builder
COPY --from=builder /install /usr/local

# Alpine needs libpq at runtime to talk to Postgres
RUN apk add --no-cache libpq

# Copy only the code folder
COPY ./app ./app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]