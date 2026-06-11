#!/bin/bash
set -euo pipefail

# Development-only runner. Binds to localhost and enables Flask debug mode.
# Use the systemd/gunicorn configuration for production deployments.
uv sync
port=$(
  uv run python3 - <<'PY'
import socket

for port in range(5000, 5100):
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            continue
        print(port)
        break
else:
    raise SystemExit("No free localhost port found in 5000-5099")
PY
)
echo "Starting LTDB development server on http://127.0.0.1:${port}"
uv run flask --app wsgi:app run --host 127.0.0.1 --port "${port}" --debug
