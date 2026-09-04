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

FAILED_RUNS=0
ANALYZED_RUNS=0
for i in $(seq 1 "$RUNS"); do
  echo "[RUN $i] start $(TZ=Asia/Seoul date '+%F %T %Z')" | tee -a "$SUMMARY_LOG"

  if "$SCRIPT_DIR/run_experiment.sh" "$i" > "$LOG_DIR/run_${i}.console.out" 2> "$LOG_DIR/run_${i}.console.err"; then
    :
  else
    rc=$?
    echo "[RUN $i] experiment FAIL rc=$rc" | tee -a "$SUMMARY_LOG"
    FAILED_RUNS=$((FAILED_RUNS + 1))
    continue
  fi

  analyzer="$REPO_ROOT/analysis/plot_step17_tinyllama_infer_load.py"
  if python3 "$analyzer" --step "$STEP_NAME" --run "$i" \
    >> "$LOG_DIR/run_${i}.analysis.out" 2>> "$LOG_DIR/run_${i}.analysis.err"; then
    :
  else
    rc=$?
    echo "[RUN $i] analysis FAIL rc=$rc" | tee -a "$SUMMARY_LOG"
    FAILED_RUNS=$((FAILED_RUNS + 1))
    continue
  fi

  ANALYZED_RUNS=$((ANALYZED_RUNS + 1))
  echo "[RUN $i] experiment+analysis OK" | tee -a "$SUMMARY_LOG"
done

distribution="$REPO_ROOT/analysis/plot_step17_tinyllama_infer_load_distribution.py"
if (( ANALYZED_RUNS > 0 )); then
  if python3 "$distribution" --step "$STEP_NAME" --runs "$RUNS" >> "$SUMMARY_LOG" 2>&1; then
    :
  else
    rc=$?
    echo "[ALL] distribution analysis FAIL rc=$rc" | tee -a "$SUMMARY_LOG"
    FAILED_RUNS=$((FAILED_RUNS + 1))
  fi
fi

echo "[ALL] end analyzed=$ANALYZED_RUNS failures=$FAILED_RUNS $(TZ=Asia/Seoul date '+%F %T %Z')" | tee -a "$SUMMARY_LOG"
if (( FAILED_RUNS > 0 )); then
  exit 1
fi
