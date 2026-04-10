#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# stop_loop.sh — stop the Sovereign benchmark loop
#
# Usage:
#   ./stop_loop.sh
# ──────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="$(dirname "$SCRIPT_DIR")/.loop-state"
PID_FILE="$STATE_DIR/.loop.pid"

if [[ -f "$PID_FILE" ]]; then
  PID=$(cat "$PID_FILE")
  if kill -0 "$PID" 2>/dev/null; then
    echo "Stopping loop (PID $PID)..."
    kill "$PID"
    sleep 2
    kill -0 "$PID" 2>/dev/null && echo "WARN: Process still alive after SIGTERM, sending SIGKILL" && kill -9 "$PID"
    echo "Loop stopped."
  else
    echo "Loop not running (PID $PID is dead)."
  fi
  rm -f "$PID_FILE"
else
  echo "No PID file found. Loop not running, or state dir missing."
fi
