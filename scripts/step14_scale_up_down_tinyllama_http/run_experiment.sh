#!/usr/bin/env bash
set -euo pipefail

STEP="step14_scale_up_down_tinyllama_http"
RUN_ID="${1:-1}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

LOG_DIR="${REPO_ROOT}/logs/redacted/${STEP}"
DATA_DIR="${REPO_ROOT}/data/netdata/${STEP}/run_${RUN_ID}"
RESULT_DIR="${REPO_ROOT}/results/${STEP}/run_${RUN_ID}"

mkdir -p "${LOG_DIR}" "${DATA_DIR}" "${RESULT_DIR}"

LOG_FILE="${LOG_DIR}/run_${RUN_ID}.log"
REQ_CSV="${LOG_DIR}/run_${RUN_ID}_requests.csv"

NAMESPACE="${NAMESPACE:-default}"
DEPLOY="${DEPLOY:-tinyllama-server}"
SVC="${SVC:-tinyllama-service}"
SELECTOR="${SELECTOR:-app=tinyllama}"

REPLICAS_HIGH="${REPLICAS_HIGH:-3}"
REPLICAS_LOW="${REPLICAS_LOW:-1}"

DURATION_SEC="${DURATION_SEC:-300}"
HTTP_TIMEOUT_SEC="${HTTP_TIMEOUT_SEC:-300}"

LOAD_DURATION_SEC="${LOAD_DURATION_SEC:-30}"
LOAD_RPS="${LOAD_RPS:-1}"

NODEPORT="${NODEPORT:-30080}"
ENDPOINT_PATH="${ENDPOINT_PATH:-/v1/chat/completions}"
MODEL_NAME="${MODEL_NAME:-tinyllama}"

STEP12_DIR="${STEP12_DIR:-${REPO_ROOT}/scripts/step12_apply_tinyllama_http}"
DEPLOY_YAML="${DEPLOY_YAML:-${STEP12_DIR}/tinyllama-deployment.yaml}"
SVC_YAML="${SVC_YAML:-${STEP12_DIR}/tinyllama-service.yaml}"
PROMPTS_FILE="${PROMPTS_FILE:-${STEP12_DIR}/prompts_10.txt}"

NETDATA_URL="${NETDATA_URL:-http://127.0.0.1:19999}"
CPU_CHART="${CPU_CHART:-system.cpu}"
RAM_CHART="${RAM_CHART:-system.ram}"
DISK_UTIL_CHART="${DISK_UTIL_CHART:-disk_util.mmcblk0}"
NET_CHART="${NET_CHART:-net.eth0}"

require_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "missing command: $1" >&2; exit 1; }; }
require_cmd kubectl
require_cmd curl
require_cmd date
require_cmd python3

print_kst_now() { TZ="Asia/Seoul" date "+%Y-%m-%d %H:%M:%S KST"; }
epoch_to_kst() { TZ="Asia/Seoul" date -d "@$1" "+%Y-%m-%d %H:%M:%S KST"; }

calc_points() {
  local after="$1" before="$2"
  local dur=$((before - after))
  local p=$(( (dur + 4) / 5 ))
  (( p < 2 )) && p=2
  echo "${p}"
}

export_csv() {
  local chart="$1" after="$2" before="$3" out="$4"
  local points; points="$(calc_points "${after}" "${before}")"
  curl -sS --max-time 10 -G "${NETDATA_URL}/api/v1/data" \
    --data-urlencode "chart=${chart}" \
    --data-urlencode "after=${after}" \
    --data-urlencode "before=${before}" \
    --data-urlencode "group=average" \
    --data-urlencode "points=${points}" \
    --data-urlencode "format=csv" \
    --data-urlencode "options=seconds,flip" \
    > "${out}" || true
  if head -n 1 "${out}" 2>/dev/null | grep -q "No metrics where matched"; then
    : > "${out}"
  fi
}

json_payload() {
  local prompt="$1"
  python3 - "${MODEL_NAME}" "${prompt}" <<'PY'
import json, sys
model = sys.argv[1]
prompt = sys.argv[2]
payload = {
  "model": model,
  "messages": [{"role": "user", "content": prompt}],
  "max_tokens": 64
}
print(json.dumps(payload))
PY
}

get_any_pod() {
  kubectl -n "${NAMESPACE}" get pods -l "${SELECTOR}" \
    --field-selector=status.phase=Running \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true
}

get_pod_hostip() {
  local pod="$1"
  kubectl -n "${NAMESPACE}" get pod "${pod}" -o jsonpath='{.status.hostIP}' 2>/dev/null || true
}

wait_http_200() {
  local timeout="${1:-300}"
  local elapsed=0
  while (( elapsed < timeout )); do
    local pod ip code payload
    pod="$(get_any_pod)"
    if [[ -n "${pod}" ]]; then
      ip="$(get_pod_hostip "${pod}")"
      if [[ -n "${ip}" ]]; then
        payload="$(json_payload "hi")"
        code="$(curl -s -o /dev/null -w "%{http_code}" \
          -X POST "http://${ip}:${NODEPORT}${ENDPOINT_PATH}" \
          -H "Content-Type: application/json" \
          -d "${payload}" \
          --connect-timeout 5 --max-time 30 || true)"
        if [[ "${code}" == "200" ]]; then
          echo "${ip}"
          return 0
        fi
      fi
    fi
    sleep 5
    elapsed=$((elapsed + 5))
  done
  return 1
}

kubectl wait --for=condition=Ready nodes --all --timeout=180s >/dev/null

if [[ ! -f "${DEPLOY_YAML}" ]] || [[ ! -f "${SVC_YAML}" ]]; then
  echo "missing yaml: ${DEPLOY_YAML} or ${SVC_YAML}" >&2
  exit 1
fi

if ! kubectl -n "${NAMESPACE}" get deploy "${DEPLOY}" >/dev/null 2>&1; then
  kubectl -n "${NAMESPACE}" apply -f "${DEPLOY_YAML}" -f "${SVC_YAML}" >/dev/null
fi
if ! kubectl -n "${NAMESPACE}" get svc "${SVC}" >/dev/null 2>&1; then
  kubectl -n "${NAMESPACE}" apply -f "${SVC_YAML}" >/dev/null
fi

kubectl -n "${NAMESPACE}" scale deploy "${DEPLOY}" --replicas="${REPLICAS_LOW}" >/dev/null
kubectl -n "${NAMESPACE}" rollout status deploy "${DEPLOY}" --timeout=600s >/dev/null

BASE_IP="$(wait_http_200 "${HTTP_TIMEOUT_SEC}")" || { echo "HTTP not ready at replicas=${REPLICAS_LOW}" >&2; exit 1; }

START_EPOCH="$(date +%s)"
END_TARGET_EPOCH="$((START_EPOCH + DURATION_SEC))"

{
  echo "STEP=${STEP}"
  echo "RUN=${RUN_ID}"
  echo "START_EPOCH=${START_EPOCH}"
  echo "START_KST=$(epoch_to_kst "${START_EPOCH}")"
  echo "END_TARGET_EPOCH=${END_TARGET_EPOCH}"
  echo "END_TARGET_KST=$(epoch_to_kst "${END_TARGET_EPOCH}")"
  echo "REPLICAS_LOW=${REPLICAS_LOW}"
  echo "REPLICAS_HIGH=${REPLICAS_HIGH}"
  echo "NODEPORT=${NODEPORT}"
  echo "ENDPOINT_PATH=${ENDPOINT_PATH}"
  echo "NETDATA_URL=${NETDATA_URL}"
} > "${LOG_FILE}"

SCALE_UP_START_EPOCH="${START_EPOCH}"
kubectl -n "${NAMESPACE}" scale deploy "${DEPLOY}" --replicas="${REPLICAS_HIGH}" >/dev/null
kubectl -n "${NAMESPACE}" rollout status deploy "${DEPLOY}" --timeout=600s >/dev/null

BASE_IP="$(wait_http_200 "${HTTP_TIMEOUT_SEC}")" || { echo "HTTP not ready after scale up" >&2; exit 1; }
READY_EPOCH="$(date +%s)"

{
  echo "SCALE_UP_START_EPOCH=${SCALE_UP_START_EPOCH}"
  echo "READY_EPOCH=${READY_EPOCH}"
  echo "READY_KST=$(epoch_to_kst "${READY_EPOCH}")"
  echo "T_scale_up=$((READY_EPOCH - SCALE_UP_START_EPOCH))"
} >> "${LOG_FILE}"

echo "idx,epoch,kst,http_code,time_total,remote_ip,remote_port" > "${REQ_CSV}"

LOAD_START_EPOCH="$(date +%s)"
echo "LOAD_START_EPOCH=${LOAD_START_EPOCH}" >> "${LOG_FILE}"
echo "LOAD_START_KST=$(epoch_to_kst "${LOAD_START_EPOCH}")" >> "${LOG_FILE}"

mapfile -t PROMPTS_ARR < "${PROMPTS_FILE}"
if (( ${#PROMPTS_ARR[@]} < 1 )); then
  PROMPTS_ARR=("hi")
fi

REQS_TOTAL="$((LOAD_DURATION_SEC * LOAD_RPS))"
(( REQS_TOTAL < 1 )) && REQS_TOTAL=1

for i in $(seq 1 "${REQS_TOTAL}"); do
  idx=$(( (i - 1) % ${#PROMPTS_ARR[@]} ))
  prompt="${PROMPTS_ARR[${idx}]}"
  payload="$(json_payload "${prompt}")"

  metrics="$(curl -s -o /dev/null -w "%{http_code},%{time_total},%{remote_ip},%{remote_port}" \
    -X POST "http://${BASE_IP}:${NODEPORT}${ENDPOINT_PATH}" \
    -H "Content-Type: application/json" \
    -d "${payload}" \
    --connect-timeout 5 --max-time 60 || true)"

  now_epoch="$(date +%s)"
  now_kst="$(epoch_to_kst "${now_epoch}")"

  IFS=',' read -r http_code time_total remote_ip remote_port <<< "${metrics}"
  echo "${i},${now_epoch},${now_kst},${http_code},${time_total},${remote_ip},${remote_port}" >> "${REQ_CSV}"

  sleep 1
done

LOAD_END_EPOCH="$(date +%s)"
{
  echo "LOAD_END_EPOCH=${LOAD_END_EPOCH}"
  echo "LOAD_END_KST=$(epoch_to_kst "${LOAD_END_EPOCH}")"
  echo "T_load=$((LOAD_END_EPOCH - LOAD_START_EPOCH))"
} >> "${LOG_FILE}"

SCALE_DOWN_START_EPOCH="$(date +%s)"
kubectl -n "${NAMESPACE}" scale deploy "${DEPLOY}" --replicas="${REPLICAS_LOW}" >/dev/null
kubectl -n "${NAMESPACE}" rollout status deploy "${DEPLOY}" --timeout=600s >/dev/null
BASE_IP="$(wait_http_200 "${HTTP_TIMEOUT_SEC}")" || { echo "HTTP not ready after scale down" >&2; exit 1; }
SCALE_DOWN_END_EPOCH="$(date +%s)"

{
  echo "SCALE_DOWN_START_EPOCH=${SCALE_DOWN_START_EPOCH}"
  echo "SCALE_DOWN_END_EPOCH=${SCALE_DOWN_END_EPOCH}"
  echo "T_scale_down=$((SCALE_DOWN_END_EPOCH - SCALE_DOWN_START_EPOCH))"
} >> "${LOG_FILE}"

now_epoch="$(date +%s)"
if (( now_epoch < END_TARGET_EPOCH )); then
  sleep "$((END_TARGET_EPOCH - now_epoch))"
  END_EPOCH="${END_TARGET_EPOCH}"
  OVERRUN=0
else
  END_EPOCH="${now_epoch}"
  OVERRUN=1
fi

{
  echo "END_EPOCH=${END_EPOCH}"
  echo "END_KST=$(epoch_to_kst "${END_EPOCH}")"
  echo "OVERRUN=${OVERRUN}"
  echo "T_total=$((END_EPOCH - START_EPOCH))"
  echo "T_ready=$((READY_EPOCH - START_EPOCH))"
} >> "${LOG_FILE}"

export_csv "${CPU_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${DATA_DIR}/system_cpu.csv"
export_csv "${RAM_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${DATA_DIR}/system_ram.csv"
export_csv "${DISK_UTIL_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${DATA_DIR}/disk_util_mmcblk0.csv"
export_csv "${NET_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${DATA_DIR}/net_eth0.csv"

cp "${LOG_FILE}" "${RESULT_DIR}/redacted.log"

echo "[${STEP}] run_${RUN_ID} done. START=$(epoch_to_kst "${START_EPOCH}") END=$(epoch_to_kst "${END_EPOCH}")"
