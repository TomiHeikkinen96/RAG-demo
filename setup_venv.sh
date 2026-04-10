#!/usr/bin/env bash

VENV_DIR=".venv"
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
REQUIREMENTS_FILE="requirements.txt"

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  IS_SOURCED=1
else
  IS_SOURCED=0
fi

fail() {
  echo "Error: $1" >&2
  if [ "$IS_SOURCED" -eq 1 ]; then
    return 1
  fi
  exit 1
}

if ! command -v python3 >/dev/null 2>&1; then
  fail "python3 is not installed or not on PATH."
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment in $VENV_DIR"
  python3 -m venv "$VENV_DIR" || fail "failed to create virtual environment."
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate" || fail "failed to activate virtual environment."

echo "Virtual environment active: $VIRTUAL_ENV"

python -m pip install --upgrade pip || fail "failed to upgrade pip."

if [ -f "$REQUIREMENTS_FILE" ]; then
  echo "Installing dependencies from $REQUIREMENTS_FILE"
  python -m pip install -r "$REQUIREMENTS_FILE" || fail "failed to install requirements."
else
  echo "No requirements file found, skipping dependency install."
fi

echo
echo "Environment ready."
if [ "$IS_SOURCED" -eq 1 ]; then
  echo "The virtual environment is active in this shell."
else
  echo "Run this command to activate it in your current shell:"
  echo "source ./$SCRIPT_NAME"
fi
