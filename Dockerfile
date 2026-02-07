# --- Build Stage ---
FROM python:3.11-slim AS builder

# ... (apt-get commands stay the same) ...

WORKDIR /app
COPY requirements.txt .

# This command will now succeed because en_core_web_md is gone from the file
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# This command handles the model download via a direct link
RUN PATH="/install/bin:$PATH" PYTHONPATH="/install/lib/python3.11/site-packages" \
    pip install --no-cache-dir --prefix=/install \
    https://github.com/explosion/spacy-models/releases/download/en_core_web_md-3.8.0/en_core_web_md-3.8.0-py3-none-any.whl