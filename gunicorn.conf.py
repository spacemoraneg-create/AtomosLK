import os

# Atomos Production Gunicorn Configuration
port = os.environ.get("PORT", "10000")
bind = f"0.0.0.0:{port}"

# Concurrency
workers = 2
threads = 4
worker_class = "gthread"

# Timeouts - 120s ensures deep multi-turn LLM reasoning never times out
timeout = 120
graceful_timeout = 30
keepalive = 5

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
