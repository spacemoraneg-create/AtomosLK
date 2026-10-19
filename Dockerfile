FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code and web assets
COPY src/ /app/src/
COPY web/ /app/web/
COPY scripts/ /app/scripts/
COPY tests/ /app/tests/
COPY pyproject.toml gunicorn.conf.py wsgi.py /app/

# Ensure data directory exists with SQLite database
COPY data/ /app/data/

EXPOSE 5000

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

# Start production server using gunicorn config
CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]

