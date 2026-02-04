#!/usr/bin/env bash
set -euo pipefail

# ===== Fixed params (from spec) =====
PING_COUNT=20
PING_INTERVAL=0.2
IPERF_DURATION=10
IPERF_STREAMS=1
COOLDOWN=30

# ===== Step name (no "benchmark") =====
STEP_NAME="step11_network"

# ===== Workers =====
# format: "name ip"
WORKERS=(
  "pi03 100.70.165.30"
  "pi04 100.67.201.85"
  "yhsensorpi 100.117.253.4"
)

RUN_IDX="${1:-}"
if [[ -z "${RUN_IDX}" ]]; then
  echo "Usage: $0 <run_index>"
  exit 1
fi

RUN_DIR_DATA="data/network/${STEP_NAME}/run_${RUN_IDX}"
RUN_LOG="logs/redacted/${STEP_NAME}/run_${RUN_IDX}.log"
mkdir -p "${RUN_DIR_DATA}"
mkdir -p "$(dirname "${RUN_LOG}")"

START_EPOCH="$(date +%s)"
{
  echo "STEP=${STEP_NAME}"
  echo "RUN_IDX=${RUN_IDX}"
  echo "START_EPOCH=${START_EPOCH}"
  echo "PING_COUNT=${PING_COUNT}"
  echo "PING_INTERVAL=${PING_INTERVAL}"
  echo "IPERF_DURATION=${IPERF_DURATION}"
  echo "IPERF_STREAMS=${IPERF_STREAMS}"
  echo "COOLDOWN=${COOLDOWN}"
  echo "MASTER_HOST=$(hostname)"
  echo "MASTER_TIME_UTC=$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo
  echo "WORKERS:"
  for w in "${WORKERS[@]}"; do
    echo "  ${w}"
  done
  echo
} | tee "${RUN_LOG}"

for w in "${WORKERS[@]}"; do
  name="$(echo "${w}" | awk '{print $1}')"
  ip="$(echo "${w}" | awk '{print $2}')"

  echo "[${name}] ping -> ${ip}" | tee -a "${RUN_LOG}"
  ping -c "${PING_COUNT}" -i "${PING_INTERVAL}" "${ip}" \
    | tee "${RUN_DIR_DATA}/ping_master_to_${name}.txt" >/dev/null

  echo "[${name}] iperf3 tcp -> ${ip}" | tee -a "${RUN_LOG}"
  iperf3 -c "${ip}" -t "${IPERF_DURATION}" -P "${IPERF_STREAMS}" --json \
    | tee "${RUN_DIR_DATA}/iperf_master_to_${name}_tcp.json" >/dev/null

  echo "[${name}] cooldown ${COOLDOWN}s" | tee -a "${RUN_LOG}"
  sleep "${COOLDOWN}"
done

END_EPOCH="$(date +%s)"
T_TOTAL="$(( END_EPOCH - START_EPOCH ))"

{
  echo
  echo "END_EPOCH=${END_EPOCH}"
  echo "T_total=${T_TOTAL}"
} | tee -a "${RUN_LOG}"
