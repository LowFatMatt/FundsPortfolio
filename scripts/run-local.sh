#!/usr/bin/env bash
# Run the FundsPortfolio app locally in a virtual environment.
# Usage: ./scripts/run-local.sh [--no-venv]

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_DIR="$ROOT_DIR/.venv"
PYTHON_BIN=python

# Allow skipping venv creation for environments where dependencies are already installed
# (use ${1:-} to avoid errors when $1 is unset under `set -u`)
if [[ "${1:-}" != "--no-venv" ]]; then
  if [[ ! -d "$VENV_DIR" ]]; then
    echo "🛠 Creating virtual environment at $VENV_DIR"
    python -m venv "$VENV_DIR"
  fi
  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"
  PYTHON_BIN="$VENV_DIR/bin/python"

  echo "📦 Installing dependencies (requirements.txt)"
  "$PYTHON_BIN" -m pip install --upgrade pip
  "$PYTHON_BIN" -m pip install -r requirements.txt
else
  echo "⚠️  Skipping virtualenv setup (using system python)"
fi

export FLASK_APP=funds_portfolio.app
export FLASK_ENV=development
export FLASK_RUN_HOST=0.0.0.0
export FLASK_RUN_PORT=5000

echo "🚀 Starting Flask dev server (http://localhost:5000)"
"$PYTHON_BIN" -m flask run
