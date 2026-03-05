FROM python:3.12-slim AS base

# Install WeasyPrint system dependencies
# Note: libgdk-pixbuf2.0-0 was renamed to libgdk-pixbuf-xlib-2.0-0 in Debian Trixie
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-xlib-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-liberation \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Copy application code
COPY app/ ./app/
COPY templates/ ./templates/
COPY static/ ./static/
COPY migrations/ ./migrations/
# Create temp and data directories
RUN mkdir -p /tmp/rhone-analyzer /app/data

# Non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app /tmp/rhone-analyzer
USER appuser

# Railway sets PORT environment variable (defaults to 8000)
ENV PORT=8000
EXPOSE ${PORT}

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
