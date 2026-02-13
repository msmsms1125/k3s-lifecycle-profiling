#!/bin/bash

STEP="step12_apply_tinyllama_http"
RUN_ID=${1:-1}
BASE_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
DATA_DIR="${BASE_DIR}/data/netdata/${STEP}/run_${RUN_ID}"
RESULT_DIR="${BASE_DIR}/results/${STEP}/run_${RUN_ID}"
LOG_DIR="${BASE_DIR}/scripts/${STEP}/logs/redacted"
LOG_FILE="${LOG_DIR}/run_${RUN_ID}.log"
YAML_DIR="$(dirname "$0")"
PROMPTS="${YAML_DIR}/prompts_10.txt"
NETDATA_HOST="localhost"
NETDATA_PORT="19999"

mkdir -p "${DATA_DIR}" "${RESULT_DIR}" "${LOG_DIR}"

fetch_csv() {
  local chart="$1"
  local after="$2"
  local before="$3"
  local out="$4"
  curl -s "http://${NETDATA_HOST}:${NETDATA_PORT}/api/v1/data?chart=${chart}&after=${after}&before=${before}&format=csv" > "${out}"
}

kubectl delete deployment tinyllama-server --ignore-not-found=true
kubectl delete service tinyllama-service --ignore-not-found=true
sleep 10

START_EPOCH=$(date +%s)
echo "START_EPOCH=${START_EPOCH}" | tee "${LOG_FILE}"
echo "START_HUMAN=$(date -d @${START_EPOCH} '+%Y-%m-%d %H:%M:%S')" | tee -a "${LOG_FILE}"

kubectl apply -f "${YAML_DIR}/tinyllama-deployment.yaml" -f "${YAML_DIR}/tinyllama-service.yaml"

WORKER_IP=""
READY=0
READY_EPOCH=""
TIMEOUT=300
ELAPSED=0

while [ "${ELAPSED}" -lt "${TIMEOUT}" ]; do
  sleep 5
  ELAPSED=$((ELAPSED + 5))
  POD_NAME=$(kubectl get pods -l app=tinyllama -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
  if [ -z "${POD_NAME}" ]; then
    continue
  fi
  WORKER_IP=$(kubectl get pod "${POD_NAME}" -o jsonpath='{.status.hostIP}' 2>/dev/null)
  if [ -z "${WORKER_IP}" ]; then
    continue
  fi
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    "http://${WORKER_IP}:30080/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d '{"model":"tinyllama","messages":[{"role":"user","content":"hi"}],"max_tokens":5,"temperature":0.1}' \
    --connect-timeout 5 --max-time 30 2>/dev/null)
  if [ "${HTTP_CODE}" = "200" ]; then
    READY=1
    break
  fi
done

if [ "${READY}" -ne 1 ]; then
  echo "ERROR: Pod did not become ready within ${TIMEOUT}s" | tee -a "${LOG_FILE}"
  END_EPOCH=$(date +%s)
  echo "END_EPOCH=${END_EPOCH}" | tee -a "${LOG_FILE}"
  fetch_csv "system.cpu" "${START_EPOCH}" "${END_EPOCH}" "${DATA_DIR}/system_cpu.csv"
  fetch_csv "system.ram" "${START_EPOCH}" "${END_EPOCH}" "${DATA_DIR}/system_ram.csv"
  fetch_csv "disk.util" "${START_EPOCH}" "${END_EPOCH}" "${DATA_DIR}/disk_util_mmcblk0.csv"
  fetch_csv "net.eth0" "${START_EPOCH}" "${END_EPOCH}" "${DATA_DIR}/net_eth0.csv"
  exit 1
fi

READY_EPOCH=$(date +%s)
T_READY=$((READY_EPOCH - START_EPOCH))
echo "READY_EPOCH=${READY_EPOCH}" | tee -a "${LOG_FILE}"
echo "READY_HUMAN=$(date -d @${READY_EPOCH} '+%Y-%m-%d %H:%M:%S')" | tee -a "${LOG_FILE}"
echo "T_ready=${T_READY}" | tee -a "${LOG_FILE}"

sleep 2

LOAD_START_EPOCH=$(date +%s)
echo "LOAD_START_EPOCH=${LOAD_START_EPOCH}" | tee -a "${LOG_FILE}"
echo "LOAD_START_HUMAN=$(date -d @${LOAD_START_EPOCH} '+%Y-%m-%d %H:%M:%S')" | tee -a "${LOG_FILE}"

mapfile -t PROMPTS_ARR < "${PROMPTS}"
REQUEST_COUNT=0
TOTAL_REQUESTS=10
INTERVAL=1

for PROMPT in "${PROMPTS_ARR[@]}"; do
  if [ "${REQUEST_COUNT}" -ge "${TOTAL_REQUESTS}" ]; then
    break
  fi
  REQ_START=$(date +%s%N)
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    "http://${WORKER_IP}:30080/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"tinyllama\",\"messages\":[{\"role\":\"user\",\"content\":\"${PROMPT}\"}],\"max_tokens\":32,\"temperature\":0.1}" \
    --connect-timeout 5 --max-time 60 2>/dev/null)
  REQ_END=$(date +%s%N)
  REQ_MS=$(( (REQ_END - REQ_START) / 1000000 ))
  echo "req_${REQUEST_COUNT}: status=${HTTP_CODE} latency=${REQ_MS}ms prompt=$(echo "${PROMPT}" | cut -c1-40)" | tee -a "${LOG_FILE}"
  REQUEST_COUNT=$((REQUEST_COUNT + 1))
  REMAINING=$((INTERVAL * 1000 - REQ_MS))
  if [ "${REMAINING}" -gt 0 ]; then
    sleep "$(echo "scale=3; ${REMAINING}/1000" | bc)"
  fi
done

LOAD_END_EPOCH=$(date +%s)
T_LOAD=$((LOAD_END_EPOCH - LOAD_START_EPOCH))
echo "LOAD_END_EPOCH=${LOAD_END_EPOCH}" | tee -a "${LOG_FILE}"
echo "LOAD_END_HUMAN=$(date -d @${LOAD_END_EPOCH} '+%Y-%m-%d %H:%M:%S')" | tee -a "${LOG_FILE}"
echo "T_load=${T_LOAD}" | tee -a "${LOG_FILE}"

STABILIZE_REMAINING=$((START_EPOCH + 300 - $(date +%s)))
if [ "${STABILIZE_REMAINING}" -gt 0 ]; then
  sleep "${STABILIZE_REMAINING}"
fi

END_EPOCH=$(date +%s)
T_TOTAL=$((END_EPOCH - START_EPOCH))
echo "END_EPOCH=${END_EPOCH}" | tee -a "${LOG_FILE}"
echo "END_HUMAN=$(date -d @${END_EPOCH} '+%Y-%m-%d %H:%M:%S')" | tee -a "${LOG_FILE}"
echo "T_total=${T_TOTAL}" | tee -a "${LOG_FILE}"

fetch_csv "system.cpu" "${START_EPOCH}" "${END_EPOCH}" "${DATA_DIR}/system_cpu.csv"
fetch_csv "system.ram" "${START_EPOCH}" "${END_EPOCH}" "${DATA_DIR}/system_ram.csv"
fetch_csv "disk.util" "${START_EPOCH}" "${END_EPOCH}" "${DATA_DIR}/disk_util_mmcblk0.csv"
fetch_csv "net.eth0" "${START_EPOCH}" "${END_EPOCH}" "${DATA_DIR}/net_eth0.csv"

cp "${LOG_FILE}" "${RESULT_DIR}/redacted.log"

echo "=== run_${RUN_ID} DONE: T_ready=${T_READY}s T_total=${T_TOTAL}s ===" | tee -a "${LOG_FILE}"
