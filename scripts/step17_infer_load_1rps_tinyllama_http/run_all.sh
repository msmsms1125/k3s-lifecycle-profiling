#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
STEP_NAME="$(basename "$SCRIPT_DIR")"

RUNS="${RUNS:-10}"

LOG_DIR="$REPO_ROOT/logs/redacted/$STEP_NAME"
mkdir -p "$LOG_DIR"

SUMMARY_LOG="$LOG_DIR/run_all_summary.log"
: > "$SUMMARY_LOG"

echo "[ALL] start $(TZ=Asia/Seoul date '+%F %T %Z')" | tee -a "$SUMMARY_LOG"

FAIL=0
for i in $(seq 1 "$RUNS"); do
  echo "[RUN $i] start $(TZ=Asia/Seoul date '+%F %T %Z')" | tee -a "$SUMMARY_LOG"

  if "$SCRIPT_DIR/run_experiment.sh" "$i" > "$LOG_DIR/run_${i}.console.out" 2> "$LOG_DIR/run_${i}.console.err"; then
    echo "[RUN $i] run_experiment ok $(TZ=Asia/Seoul date '+%F %T %Z')" | tee -a "$SUMMARY_LOG"
  else
    RC=$?
    echo "[RUN $i] run_experiment FAIL rc=$RC $(TZ=Asia/Seoul date '+%F %T %Z')" | tee -a "$SUMMARY_LOG"
    FAIL=1
    continue
  fi

  P1="$REPO_ROOT/analysis/plot_step17_tinyllama_infer_load.py"
  if [[ -f "$P1" ]]; then
    python3 "$P1" --step "$STEP_NAME" --run "$i" >> "$LOG_DIR/run_${i}.analysis.out" 2>> "$LOG_DIR/run_${i}.analysis.err" || true
  fi

  echo "[RUN $i] done  $(TZ=Asia/Seoul date '+%F %T %Z')" | tee -a "$SUMMARY_LOG"
done

P2="$REPO_ROOT/analysis/plot_step17_tinyllama_infer_load_distribution.py"
if [[ -f "$P2" ]]; then
  python3 "$P2" --step "$STEP_NAME" --runs "$RUNS" >> "$SUMMARY_LOG" 2>&1 || true
fi

echo "[ALL] end   $(TZ=Asia/Seoul date '+%F %T %Z')" | tee -a "$SUMMARY_LOG"
exit "$FAIL"
