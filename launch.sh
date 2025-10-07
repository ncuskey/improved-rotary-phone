#!/usr/bin/env bash
# Improved Rotary Phone (ISBN Lot Optimizer) launcher
# - Works from anywhere by resolving its own location
# - Ensures the correct virtual environment exists
# - Installs/updates requirements
# - Launches the app entrypoint: `python -m isbn_lot_optimizer`
#
# Usage:
#   ./launch.sh [app args...]
# Examples:
#   ./launch.sh
#   ./launch.sh --no-gui --scan 9780316769488 --condition "Very Good"

set -Eeuo pipefail

# Resolve this script's real directory (supports symlinks)
SOURCE="${BASH_SOURCE[0]:-$0}"
while [ -h "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null && pwd)"

# Project layout:
#   repo root (this script is in bin/, project is in ISBN/)
#   └── ISBN/
#       ├── requirements.txt
#       └── isbn_lot_optimizer/  (python package)
PROJECT_DIR="$SCRIPT_DIR/../ISBN"
PKG_DIR="$PROJECT_DIR/isbn_lot_optimizer"
REQUIREMENTS="$PROJECT_DIR/requirements.txt"
VENV_DIR="$PROJECT_DIR/.venv"

if [ ! -d "$PKG_DIR" ]; then
  echo "Error: could not find package directory at: $PKG_DIR" >&2
  exit 1
fi

# Choose a system python to build the venv (pyenv users: ensure local version via .python-version)
SYSTEM_PYTHON="${SYSTEM_PYTHON:-python3}"

# Create venv if missing
if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "[launcher] Creating virtual environment at $VENV_DIR"
  "$SYSTEM_PYTHON" -m venv "$VENV_DIR"
fi

PY="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"

# Upgrade pip tooling quietly
echo "[launcher] Ensuring pip/setuptools/wheel are up to date"
"$PY" -m pip install --upgrade --quiet pip setuptools wheel

# Install requirements (idempotent; skips already satisfied)
if [ -f "$REQUIREMENTS" ]; then
  echo "[launcher] Installing/updating dependencies from requirements.txt"
  "$PY" -m pip install --requirement "$REQUIREMENTS"
fi

# Optional: load environment from .env at repo root if you want shell-level exports.
# Many apps use python-dotenv and load this automatically inside Python, so this is not required.
# Uncomment if needed:
# if [ -f "$SCRIPT_DIR/.env" ]; then
#   set -a
#   # shellcheck disable=SC1090
#   source "$SCRIPT_DIR/.env"
#   set +a
# fi

# Start the token broker if not already running
if [ -x "$PROJECT_DIR/token-broker/start-broker.sh" ]; then
  "$PROJECT_DIR/token-broker/start-broker.sh" || true
fi

# Run the application from the project directory so relative paths behave as expected
cd "$PROJECT_DIR"

echo "[launcher] Starting app: python -m isbn_lot_optimizer $*"
exec "$PY" -m isbn_lot_optimizer "$@"
