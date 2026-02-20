#!/usr/bin/env bash
set -euo pipefail

STEP_NAME="step15_rollout_restart_tinyllama_http"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

RUNS="${RUNS:-10}"

LOG_DIR="${REPO_ROOT}/logs/redacted/${STEP_NAME}"
mkdir -p "${LOG_DIR}"

SUMMARY_LOG="${LOG_DIR}/run_all_summary.log"
: > "${SUMMARY_LOG}"

echo "STEP=${STEP_NAME}" | tee -a "${SUMMARY_LOG}"
echo "RUNS=${RUNS}" | tee -a "${SUMMARY_LOG}"

for i in $(seq 1 "${RUNS}"); do
  echo "===== RUN ${i} =====" | tee -a "${SUMMARY_LOG}"
  "${SCRIPT_DIR}/run_experiment.sh" "${i}" >> "${SUMMARY_LOG}" 2>&1
done

# plots + stats (Fig1/Stats per run, Fig2/Summary per step)
for i in $(seq 1 "${RUNS}"); do
  python3 "${REPO_ROOT}/analysis/plot_step15_tinyllama_rollout_restart.py" \
    --step "${STEP_NAME}" --run "${i}" >> "${SUMMARY_LOG}" 2>&1
done

python3 "${REPO_ROOT}/analysis/plot_step15_tinyllama_rollout_restart_distribution.py" \
  --step "${STEP_NAME}" --runs "${RUNS}" >> "${SUMMARY_LOG}" 2>&1

echo "OK: all runs + plots done"
echo "SUMMARY_LOG=${SUMMARY_LOG}"
