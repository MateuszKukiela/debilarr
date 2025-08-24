# Minimal, production-ish image
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Add a non-root user
RUN useradd -m -u 10001 appuser

WORKDIR /app
COPY app.py /app/app.py

# Install runtime deps
RUN pip install --no-cache-dir requests

# Drop privileges
USER appuser

# Default command (override with args/env in docker-compose)
CMD ["python", "/app/app.py"]
