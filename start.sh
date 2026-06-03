#!/bin/bash

set -euo pipefail

handle_exit() {
    kill -TERM "$main_pid" 2>/dev/null
}

trap handle_exit TERM INT

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${INSTALL_DIR:-$SCRIPT_DIR}"

MAIN_LOG_DIR="$INSTALL_DIR/logs/main"
mkdir -p "$MAIN_LOG_DIR"

MAIN_LOGFILE="$MAIN_LOG_DIR/$(date +%Y%m%d%H%M%S)-main.log"
ERROR_LOGFILE="$INSTALL_DIR/logs/error.log"

if ! source "$INSTALL_DIR/venv/bin/activate" 2>>"$ERROR_LOGFILE"; then
    echo "$(date -Iseconds) Failed to activate venv at $INSTALL_DIR/venv" >>"$ERROR_LOGFILE"
    exit 1
fi

"$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/main.py" >>"$MAIN_LOGFILE" 2>&1 &
main_pid=$!

wait "$main_pid"