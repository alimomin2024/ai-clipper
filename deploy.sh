#!/usr/bin/env bash
set -euo pipefail

echo "🚀 Deploying AI Clipper Production Server..."

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
cd "$BACKEND_DIR"

# Ensure persistent directories exist before the worker starts.
mkdir -p storage/downloads storage/clips storage/subtitles storage/thumbnails

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8080}"
ENVIRONMENT="${ENVIRONMENT:-production}"
export PORT ENVIRONMENT
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-$BACKEND_DIR/.venv}"

if [[ "${ENVIRONMENT}" == "production" && -z "${ADMIN_API_KEY:-}" ]]; then
  echo "Warning: ADMIN_API_KEY is not set; Operations will remain locked until it is configured." >&2
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Python executable '${PYTHON_BIN}' was not found. Install Python 3.11+ or set PYTHON_BIN." >&2
  exit 1
fi

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "Creating virtual environment at ${VENV_DIR}..."
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

if [[ "${SKIP_INSTALL:-0}" != "1" ]]; then
  echo "Installing backend requirements..."
  if ! "${VENV_DIR}/bin/python" -m pip --version >/dev/null 2>&1; then
    echo "Bootstrapping pip in ${VENV_DIR}..."
    "${VENV_DIR}/bin/python" -m ensurepip --upgrade
  fi
  "${VENV_DIR}/bin/python" -m pip install --upgrade pip
  "${VENV_DIR}/bin/python" -m pip install -r requirements.txt
fi

UVICORN_BIN="${UVICORN_BIN:-${VENV_DIR}/bin/uvicorn}"
if [[ ! -x "${UVICORN_BIN}" ]]; then
  echo "Uvicorn executable not found at ${UVICORN_BIN}; dependency installation did not complete." >&2
  exit 1
fi

# Start one process unless a durable, shared queue is configured for multi-worker operation.
echo "Starting FastAPI server on http://${HOST}:${PORT}..."
exec "${UVICORN_BIN}" main:app --host "${HOST}" --port "${PORT}"
