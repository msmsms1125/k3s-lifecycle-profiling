#!/usr/bin/env bash
set -euo pipefail

STEP="step16_delete_tinyllama_http_deployment"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

LOG_DIR="${REPO_ROOT}/logs/redacted/${STEP}"
mkdir -p "${LOG_DIR}"

SUMMARY_LOG="${LOG_DIR}/run_all_summary.log"
exec > >(tee -a "${SUMMARY_LOG}") 2>&1

RUNS="${RUNS:-10}"

echo "STEP=${STEP}"
echo "RUNS=${RUNS}"
date -Is

for i in $(seq 1 "${RUNS}"); do
  echo "=== RUN ${i}/${RUNS} ==="
  bash "${REPO_ROOT}/scripts/${STEP}/run_experiment.sh" "${i}" \
    > "${LOG_DIR}/run_${i}.console.out" \
    2> "${LOG_DIR}/run_${i}.console.err"
done

echo "=== DISTRIBUTION (Fig2 + summary.csv) ==="
python3 "${REPO_ROOT}/analysis/plot_step16_tinyllama_delete_deployment_distribution.py" --step "${STEP}" --runs "${RUNS}"

echo "DONE"
