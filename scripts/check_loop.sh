#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# check_loop.sh — verify loop health and print status
#
# Usage:
#   ./check_loop.sh
# ──────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="$(dirname "$SCRIPT_DIR")/.loop-state"
PID_FILE="$STATE_DIR/.loop.pid"
HEARTBEAT_FILE="$STATE_DIR/.loop.heartbeat"
LOG_FILE="$STATE_DIR/loop.log"

echo "╔══════════════════════════════════════╗"
echo "║  Sovereign Benchmark Loop — Status     ║"
echo "╚══════════════════════════════════════╝"

if [[ -f "$PID_FILE" ]]; then
  PID=$(cat "$PID_FILE")
  if kill -0 "$PID" 2>/dev/null; then
    echo "  Loop: RUNNING (PID $PID)"
  else
    echo "  Loop: STALE PID file (PID $PID is dead — run stop_loop.sh)"
  fi
else
  echo "  Loop: NOT RUNNING (no PID file)"
fi

if [[ -f "$HEARTBEAT_FILE" ]]; then
  echo "  Heartbeat:"
  cat "$HEARTBEAT_FILE" | sed 's/^/    /'
  AGE=$(($(date +%s) - $(stat -c %Y "$HEARTBEAT_FILE" 2>/dev/null || stat -f %m "$HEARTBEAT_FILE" 2>/dev/null))))
  echo "    age: ${AGE}s ago"
  if [[ "$AGE" -gt 600 ]]; then
    echo "    ⚠ WARNING: heartbeat is stale (>10 min old)"
  fi
else
  echo "  Heartbeat: none"
fi

if [[ -f "$LOG_FILE" ]]; then
  LINES=$(wc -l < "$LOG_FILE")
  echo "  Log: $LOG_FILE ($LINES lines)"
  echo "  Last 5 log entries:"
  tail -5 "$LOG_FILE" | sed 's/^/    /'
else
  echo "  Log: none"
fi

echo ""
echo "  Ollama health:"
curl -s --max-time 3 http://localhost:11434/api/tags > /dev/null 2>&1 \
  && echo "    ✓ Responding" \
  || echo "    ✗ Unreachable"
