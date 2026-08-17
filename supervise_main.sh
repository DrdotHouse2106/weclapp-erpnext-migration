#!/bin/bash
# Self-healing supervisor for main.py: restarts it automatically whenever its log
# goes stale for too long (network dying during system sleep leaves main.py hung
# on a dead connection despite the per-request timeout - see CLAUDE.md).
cd "$(dirname "$0")"
source venv/bin/activate

STALE_SECS=1200
export PYTHONUNBUFFERED=1
SUP_LOG=/tmp/migration_supervisor.log

echo "$(date) Supervisor started" >> "$SUP_LOG"

while true; do
  RUNLOG="/tmp/migration_run_$(date +%s).log"
  echo "$(date) Launching main.py, log=$RUNLOG" >> "$SUP_LOG"
  python3 main.py > "$RUNLOG" 2>&1 &
  PID=$!

  while kill -0 "$PID" 2>/dev/null; do
    sleep 30
    MTIME=$(stat -f %m "$RUNLOG" 2>/dev/null || echo 0)
    NOW=$(date +%s)
    if [ $((NOW - MTIME)) -gt $STALE_SECS ]; then
      echo "$(date) Stale for $((NOW - MTIME))s, killing pid $PID" >> "$SUP_LOG"
      kill "$PID" 2>/dev/null
      sleep 2
      kill -9 "$PID" 2>/dev/null
      break
    fi
  done

  if ! kill -0 "$PID" 2>/dev/null; then
    wait "$PID" 2>/dev/null
    EXIT_CODE=$?
    echo "$(date) main.py exited with code $EXIT_CODE" >> "$SUP_LOG"
  fi

  sleep 5
done
