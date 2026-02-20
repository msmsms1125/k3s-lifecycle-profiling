#!/usr/bin/env bash
set -euo pipefail

STEP="step14_scale_up_down_tinyllama_http"
RUNS="${RUNS:-10}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

LOG_DIR="${REPO_ROOT}/logs/redacted/${STEP}"
ALL_LOG="${LOG_DIR}/run_all_summary.log"
mkdir -p "${LOG_DIR}"

print_kst() { TZ="Asia/Seoul" date "+%Y-%m-%d %H:%M:%S KST"; }

echo "========================================" | tee "${ALL_LOG}"
echo "STEP: ${STEP}" | tee -a "${ALL_LOG}"
echo "RUNS: ${RUNS}" | tee -a "${ALL_LOG}"
echo "START(KST): $(print_kst)" | tee -a "${ALL_LOG}"
echo "========================================" | tee -a "${ALL_LOG}"

for i in $(seq 1 "${RUNS}"); do
  echo "" | tee -a "${ALL_LOG}"
  echo "--- RUN ${i}/${RUNS} START(KST): $(print_kst) ---" | tee -a "${ALL_LOG}"
  bash "${SCRIPT_DIR}/run_experiment.sh" "${i}" 2>&1 | tee -a "${ALL_LOG}"
  echo "--- RUN ${i}/${RUNS} END(KST): $(print_kst) ---" | tee -a "${ALL_LOG}"
  sleep 5
done

echo "" | tee -a "${ALL_LOG}"
echo "=== plotting Fig1/Fig2 ===" | tee -a "${ALL_LOG}"
python3 "${REPO_ROOT}/analysis/plot_step14_tinyllama_scale.py" | tee -a "${ALL_LOG}"
python3 "${REPO_ROOT}/analysis/plot_step14_tinyllama_scale_distribution.py" | tee -a "${ALL_LOG}"

echo "========================================" | tee -a "${ALL_LOG}"
echo "END(KST): $(print_kst)" | tee -a "${ALL_LOG}"
echo "========================================" | tee -a "${ALL_LOG}"
