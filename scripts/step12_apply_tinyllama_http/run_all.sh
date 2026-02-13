#!/bin/bash

STEP="step12_apply_tinyllama_http"
RUNS=10
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ALL_LOG="${BASE_DIR}/scripts/${STEP}/logs/redacted/run_all_summary.log"

mkdir -p "${BASE_DIR}/scripts/${STEP}/logs/redacted"

echo "========================================" | tee "${ALL_LOG}"
echo "STEP: ${STEP}" | tee -a "${ALL_LOG}"
echo "RUNS: ${RUNS}" | tee -a "${ALL_LOG}"
echo "START: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "${ALL_LOG}"
echo "========================================" | tee -a "${ALL_LOG}"

for i in $(seq 1 ${RUNS}); do
  echo "" | tee -a "${ALL_LOG}"
  echo "--- RUN ${i}/${RUNS} START: $(date '+%Y-%m-%d %H:%M:%S') ---" | tee -a "${ALL_LOG}"
  bash "${SCRIPT_DIR}/run_experiment.sh" "${i}" 2>&1 | tee -a "${ALL_LOG}"
  echo "--- RUN ${i}/${RUNS} END: $(date '+%Y-%m-%d %H:%M:%S') ---" | tee -a "${ALL_LOG}"
  if [ "${i}" -lt "${RUNS}" ]; then
    kubectl delete deployment tinyllama-server --ignore-not-found=true 2>/dev/null
    kubectl delete service tinyllama-service --ignore-not-found=true 2>/dev/null
    sleep 30
  fi
done

kubectl delete deployment tinyllama-server --ignore-not-found=true 2>/dev/null
kubectl delete service tinyllama-service --ignore-not-found=true 2>/dev/null

echo "" | tee -a "${ALL_LOG}"
echo "========================================" | tee -a "${ALL_LOG}"
echo "ALL RUNS COMPLETE: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "${ALL_LOG}"
echo "========================================" | tee -a "${ALL_LOG}"

RESULT_DIR="${BASE_DIR}/results/${STEP}"
echo "" | tee -a "${ALL_LOG}"
echo "=== T_ready summary ===" | tee -a "${ALL_LOG}"
for i in $(seq 1 ${RUNS}); do
  LOG="${BASE_DIR}/scripts/${STEP}/logs/redacted/run_${i}.log"
  if [ -f "${LOG}" ]; then
    TREADY=$(grep "^T_ready=" "${LOG}" | cut -d= -f2)
    TTOTAL=$(grep "^T_total=" "${LOG}" | cut -d= -f2)
    echo "run_${i}: T_ready=${TREADY}s T_total=${TTOTAL}s" | tee -a "${ALL_LOG}"
  fi
done
