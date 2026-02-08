#!/usr/bin/env bash
set -euo pipefail

# Manithy demo runner (macOS-friendly)
# - Uses python3 (pyenv setups often don't have "python")
# - PORT can be overridden (e.g., PORT=5050 ./run_web.sh)

PORT="${PORT:-5050}"

if [[ -d ".venv" ]]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

export FLASK_ENV=production
python3 -m app.web --port "$PORT"
