#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# run_experiments.sh — start the Sovereign benchmark loop
#
# What it does:
#   1. Validates Ollama is reachable
#   2. Checks for stale lock (.loop.pid from a previous run) — stale = kill it
#   3. Writes PID to .loop.pid
#   4. Launches benchmark.py every 5 minutes in a while loop
#   5. On FAIL: checks exit code, logs, optionally restarts ollama-daemon
#   6. Heartbeat written every cycle to .loop.heartbeat
#
# Usage:
#   ./run_experiments.sh          # starts loop in foreground
#   nohup ./run_experiments.sh &  # starts loop in background
#   ./stop_loop.sh                # stops loop and removes .loop.pid
#
# What to tune:
#   INTERVAL=300  → 5 minutes (seconds)
#   MAX_FAILS=3   → restart ollama after N consecutive failures
#   OLLAMA_HOST   → defaults to localhost:11434
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCHMARK_PY="$(dirname "$SCRIPT_DIR")/benchmark.py"
STATE_DIR="$(dirname "$SCRIPT_DIR")/.loop-state"

# ── Tunables ──────────────────────────────────────────────────────────────────
INTERVAL=300          # seconds between benchmark cycles
MAX_CONSECUTIVE_FAILS=3
OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
# ─────────────────────────────────────────────────────────────────────────────

mkdir -p "$STATE_DIR"
PID_FILE="$STATE_DIR/.loop.pid"
HEARTBEAT_FILE="$STATE_DIR/.loop.heartbeat"
LOG_FILE="$STATE_DIR/loop.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

# ── Validate ─────────────────────────────────────────────────────────────────
validate_ollama() {
  curl -s --max-time 5 "$OLLAMA_HOST/api/tags" > /dev/null 2>&1
}

# ── Check stale PID ───────────────────────────────────────────────────────────
check_stale() {
  if [[ -f "$PID_FILE" ]]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
      log "ERROR: Loop already running as PID $OLD_PID. Stop it first: kill $OLD_PID"
      exit 1
    else
      log "Stale PID file from previous run (PID $OLD_PID is dead). Removing."
      rm -f "$PID_FILE"
    fi
  fi
}

# ── Heartbeat ────────────────────────────────────────────────────────────────
write_heartbeat() {
  echo "pid=$$ ts=$(date -u +%Y-%m-%dT%H:%M:%SZ) cycle=$CYCLE_COUNT consecutive_fails=$CONSECUTIVE_FAILS" \
    > "$HEARTBEAT_FILE"
}

# ── Restart Ollama (last resort) ─────────────────────────────────────────────
restart_ollama() {
  log "WARN: $CONSECUTIVE_FAILS consecutive failures. Restarting ollama-daemon..."
  systemctl --user restart ollama 2>/dev/null || sudo systemctl restart ollama 2>/dev/null || {
    log "ERROR: Could not restart ollama-daemon. Check manually."
    exit 1
  }
  sleep 10
  if validate_ollama; then
    log "Ollama restarted and healthy."
    CONSECUTIVE_FAILS=0
  else
    log "ERROR: Ollama still unhealthy after restart."
    exit 1
  fi
}

# ── Main loop ────────────────────────────────────────────────────────────────
main() {
  check_stale
  echo $$ > "$PID_FILE"
  log "=== Sovereign benchmark loop started (PID $$) ==="
  log "Interval: ${INTERVAL}s | Max consecutive fails: $MAX_CONSECUTIVE_FAILS"
  log "Benchmark: $BENCHMARK_PY"

  CYCLE_COUNT=0
  CONSECUTIVE_FAILS=0

  # Keep-alive: load models into VRAM so first cycle isn't 50s cold-start
  log "Pre-warming models..."
  curl -s "$OLLAMA_HOST/api/generate" \
    -d '{"model":"qwen3.5:4b","prompt":"ping","stream":false}' > /dev/null || true

  while true; do
    CYCLE_COUNT=$((CYCLE_COUNT + 1))
    write_heartbeat
    log "─── Cycle $CYCLE_COUNT ───"

    set +e
    python3 "$BENCHMARK_PY" 2>&1 | tee -a "$LOG_FILE"
    EXIT_CODE=${PIPESTATUS[0]}
    set -e

    if [[ "$EXIT_CODE" -eq 0 ]]; then
      log "Cycle $CYCLE_COUNT: OK"
      CONSECUTIVE_FAILS=0
    else
      CONSECUTIVE_FAILS=$((CONSECUTIVE_FAILS + 1))
      log "Cycle $CYCLE_COUNT: FAIL (exit=$EXIT_CODE) — consecutive_fails=$CONSECUTIVE_FAILS"

      if [[ "$CONSECUTIVE_FAILS" -ge "$MAX_CONSECUTIVE_FAILS" ]]; then
        restart_ollama
      fi
    fi

    write_heartbeat
    log "Sleeping ${INTERVAL}s until next cycle..."
    sleep "$INTERVAL"
  done
}

main "$@"
