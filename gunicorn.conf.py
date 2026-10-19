import os

# Atomos Production Gunicorn Configuration
port = os.environ.get("PORT", "10000")
bind = f"0.0.0.0:{port}"

# Concurrency: single unified process with 8 threads guarantees shared SQLite WAL state,
# unified background ingestion job tracking, and persistent in-memory + DB caches on Render.
workers = 1
threads = 8
worker_class = "gthread"

# Timeouts - 120s ensures deep multi-turn LLM reasoning and tournament ingestion never time out
timeout = 120
graceful_timeout = 30
keepalive = 5

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
