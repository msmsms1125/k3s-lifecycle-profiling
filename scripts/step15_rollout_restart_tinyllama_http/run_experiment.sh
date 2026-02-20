#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${1:-}"
if [[ -z "${RUN_ID}" ]]; then
  echo "Usage: $0 <run_id>"
  exit 1
fi

STEP_NAME="step15_rollout_restart_tinyllama_http"

# --- absolute paths (상대경로 문제 방지) ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

LOG_DIR="${REPO_ROOT}/logs/redacted/${STEP_NAME}"
DATA_DIR="${REPO_ROOT}/data/netdata/${STEP_NAME}/run_${RUN_ID}"
RESULT_DIR="${REPO_ROOT}/results/${STEP_NAME}/run_${RUN_ID}"

mkdir -p "${LOG_DIR}" "${DATA_DIR}" "${RESULT_DIR}"

LOG_FILE="${LOG_DIR}/run_${RUN_ID}.log"
REQ_CSV="${LOG_DIR}/run_${RUN_ID}_requests.csv"

# --- k8s targets ---
NAMESPACE="${NAMESPACE:-default}"
DEPLOYMENT_NAME="${DEPLOYMENT_NAME:-}"
SVC="${SVC:-tinyllama-service}"
SELECTOR="${SELECTOR:-app=tinyllama}"

# --- HTTP endpoint (네 curl 결과 기준으로 확정) ---
ENDPOINT_PATH="${ENDPOINT_PATH:-/v1/chat/completions}"
MODEL_NAME="${MODEL_NAME:-tinyllama}"
MAX_TOKENS_READY="${MAX_TOKENS_READY:-5}"
MAX_TOKENS_LOAD="${MAX_TOKENS_LOAD:-64}"

# NodePort: env로 주면 우선 사용, 없으면 svc에서 조회, 그것도 실패하면 30080
NODEPORT="${NODEPORT:-}"

# READY: rollout status + HTTP 200
READY_TIMEOUT_SEC="${READY_TIMEOUT_SEC:-180}"

# LOAD: 1 RPS, 10 sec => 10 requests
LOAD_RPS="${LOAD_RPS:-1}"
LOAD_DURATION_SEC="${LOAD_DURATION_SEC:-10}"
RPS_INTERVAL_SEC="${RPS_INTERVAL_SEC:-1}"
PROMPTS_FILE="${PROMPTS_FILE:-${SCRIPT_DIR}/prompts_10.txt}"

# END_EPOCH = START + 300s
DURATION_SEC="${DURATION_SEC:-300}"

# --- netdata (step14 스타일) ---
NETDATA_URL="${NETDATA_URL:-http://127.0.0.1:19999}"
CPU_CHART="${CPU_CHART:-system.cpu}"
RAM_CHART="${RAM_CHART:-system.ram}"
DISK_UTIL_CHART="${DISK_UTIL_CHART:-disk_util.mmcblk0}"
NET_CHART="${NET_CHART:-net.eth0}"

# --- helpers ---
epoch_to_kst() { TZ="Asia/Seoul" date -d "@$1" "+%Y-%m-%d %H:%M:%S KST"; }

log_kv() { echo "${1}=${2}" | tee -a "${LOG_FILE}"; }

require_nonempty() {
  local name="$1"
  local val="$2"
  if [[ -z "${val}" ]]; then
    echo "ERROR: ${name} is empty. Set it via environment variable." | tee -a "${LOG_FILE}"
    exit 1
  fi
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

get_nodeport() {
  if [[ -n "${NODEPORT}" ]]; then
    echo "${NODEPORT}"
    return 0
  fi
  local np=""
  np="$(kubectl -n "${NAMESPACE}" get svc "${SVC}" -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || true)"
  if [[ -n "${np}" ]]; then
    echo "${np}"
    return 0
  fi
  echo "30080"
}

json_payload_chat() {
  local prompt="$1"
  local max_tokens="$2"
  python3 - "${MODEL_NAME}" "${prompt}" "${max_tokens}" <<'PY'
import json, sys
model = sys.argv[1]
prompt = sys.argv[2]
max_tokens = int(sys.argv[3])
payload = {
  "model": model,
  "messages": [{"role": "user", "content": prompt}],
  "max_tokens": max_tokens
}
print(json.dumps(payload))
PY
}

post_chat_once_metrics() {
  # stdout: http_code,time_total,openai_processing_ms
  local url="$1"
  local payload="$2"

  local hdr
  hdr="$(mktemp)"
  local wt
  wt="$(curl -sS -D "${hdr}" -o /dev/null \
    -w "%{http_code},%{time_total}\n" \
    -X POST "${url}" \
    -H "Content-Type: application/json" \
    -d "${payload}" \
    --connect-timeout 5 --max-time 60 || true)"

  local code time_total
  code="${wt%%,*}"
  time_total="${wt##*,}"

  local proc_ms=""
  proc_ms="$(awk -F': ' 'tolower($1)=="openai-processing-ms"{gsub("\r","",$2); print $2}' "${hdr}" | tail -n 1 || true)"
  rm -f "${hdr}"

  [[ -z "${proc_ms}" ]] && proc_ms="NA"
  echo "${code},${time_total},${proc_ms}"
}

wait_http_200_after_restart() {
  local nodeport="$1"
  local timeout="${2:-180}"
  local elapsed=0

  while (( elapsed < timeout )); do
    local pod ip payload metrics http_code
    pod="$(get_any_pod)"
    if [[ -n "${pod}" ]]; then
      ip="$(get_pod_hostip "${pod}")"
      if [[ -n "${ip}" ]]; then
        payload="$(json_payload_chat "hi" "${MAX_TOKENS_READY}")"
        metrics="$(post_chat_once_metrics "http://${ip}:${nodeport}${ENDPOINT_PATH}" "${payload}")"
        http_code="${metrics%%,*}"
        if [[ "${http_code}" == "200" ]]; then
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

calc_points() {
  local after="$1"
  local before="$2"
  local dur=$((before - after))
  local p=$(( (dur + 4) / 5 ))
  (( p < 2 )) && p=2
  echo "${p}"
}

export_csv() {
  local chart="$1" after="$2" before="$3" out="$4"
  local points
  points="$(calc_points "${after}" "${before}")"
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

# --- start ---
: > "${LOG_FILE}"
log_kv "STEP" "${STEP_NAME}"
log_kv "RUN_ID" "${RUN_ID}"
log_kv "NAMESPACE" "${NAMESPACE}"

require_nonempty "DEPLOYMENT_NAME" "${DEPLOYMENT_NAME}"

NODEPORT_EFFECTIVE="$(get_nodeport)"
log_kv "SVC" "${SVC}"
log_kv "SELECTOR" "${SELECTOR}"
log_kv "NODEPORT" "${NODEPORT_EFFECTIVE}"
log_kv "ENDPOINT_PATH" "${ENDPOINT_PATH}"
log_kv "MODEL_NAME" "${MODEL_NAME}"

# START: rollout restart 실행 시각
START_EPOCH="$(date +%s)"
END_TARGET_EPOCH="$((START_EPOCH + DURATION_SEC))"
log_kv "START_EPOCH" "${START_EPOCH}"
log_kv "START_KST" "$(epoch_to_kst "${START_EPOCH}")"
log_kv "END_TARGET_EPOCH" "${END_TARGET_EPOCH}"
log_kv "END_TARGET_KST" "$(epoch_to_kst "${END_TARGET_EPOCH}")"

# rollout restart + rollout status
kubectl -n "${NAMESPACE}" rollout restart "deployment/${DEPLOYMENT_NAME}" >> "${LOG_FILE}" 2>&1
kubectl -n "${NAMESPACE}" rollout status "deployment/${DEPLOYMENT_NAME}" --timeout=600s >> "${LOG_FILE}" 2>&1 || true

# READY: HTTP 200까지
BASE_IP="$(wait_http_200_after_restart "${NODEPORT_EFFECTIVE}" "${READY_TIMEOUT_SEC}")" || {
  log_kv "READY_EPOCH" "NA"
  log_kv "READY_KST" "NA"
  echo "ERROR: HTTP not ready (no 200) within READY_TIMEOUT_SEC=${READY_TIMEOUT_SEC}" | tee -a "${LOG_FILE}"
  exit 1
}

READY_EPOCH="$(date +%s)"
log_kv "BASE_IP" "${BASE_IP}"
log_kv "READY_EPOCH" "${READY_EPOCH}"
log_kv "READY_KST" "$(epoch_to_kst "${READY_EPOCH}")"
log_kv "T_READY_SEC" "$((READY_EPOCH - START_EPOCH))"

# LOAD
REQS_TOTAL="$((LOAD_DURATION_SEC * LOAD_RPS))"
(( REQS_TOTAL < 1 )) && REQS_TOTAL=1

echo "seq,prompt_idx,start_epoch_ms,end_epoch_ms,latency_ms,http_code,time_total_sec,openai_processing_ms" > "${REQ_CSV}"

LOAD_START_EPOCH="$(date +%s)"
log_kv "LOAD_START_EPOCH" "${LOAD_START_EPOCH}"
log_kv "LOAD_START_KST" "$(epoch_to_kst "${LOAD_START_EPOCH}")"
log_kv "LOAD_DURATION_SEC" "${LOAD_DURATION_SEC}"
log_kv "LOAD_RPS" "${LOAD_RPS}"
log_kv "REQS_TOTAL" "${REQS_TOTAL}"

mapfile -t PROMPTS_ARR < "${PROMPTS_FILE}"
if (( ${#PROMPTS_ARR[@]} < 1 )); then
  PROMPTS_ARR=("hi")
fi

for i in $(seq 1 "${REQS_TOTAL}"); do
  idx=$(( (i - 1) % ${#PROMPTS_ARR[@]} ))
  prompt="${PROMPTS_ARR[${idx}]}"
  payload="$(json_payload_chat "${prompt}" "${MAX_TOKENS_LOAD}")"

  start_ms="$(date +%s%3N)"
  metrics="$(post_chat_once_metrics "http://${BASE_IP}:${NODEPORT_EFFECTIVE}${ENDPOINT_PATH}" "${payload}")"
  end_ms="$(date +%s%3N)"
  latency_ms=$((end_ms - start_ms))

  IFS=',' read -r http_code time_total proc_ms <<< "${metrics}"
  echo "${i},${idx},${start_ms},${end_ms},${latency_ms},${http_code},${time_total},${proc_ms}" >> "${REQ_CSV}"

  sleep "${RPS_INTERVAL_SEC}"
done

LOAD_END_EPOCH="$(date +%s)"
log_kv "LOAD_END_EPOCH" "${LOAD_END_EPOCH}"
log_kv "LOAD_END_KST" "$(epoch_to_kst "${LOAD_END_EPOCH}")"
log_kv "T_LOAD_SEC" "$((LOAD_END_EPOCH - LOAD_START_EPOCH))"

# END (target=START+300, overruns 처리)
now_epoch="$(date +%s)"
if (( now_epoch < END_TARGET_EPOCH )); then
  sleep "$((END_TARGET_EPOCH - now_epoch))"
  END_EPOCH="${END_TARGET_EPOCH}"
  OVERRUN=0
else
  END_EPOCH="${now_epoch}"
  OVERRUN=1
fi

log_kv "END_EPOCH" "${END_EPOCH}"
log_kv "END_KST" "$(epoch_to_kst "${END_EPOCH}")"
log_kv "OVERRUN" "${OVERRUN}"
log_kv "T_TOTAL_SEC" "$((END_EPOCH - START_EPOCH))"

# netdata export
export_csv "${CPU_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${DATA_DIR}/system_cpu.csv"
export_csv "${RAM_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${DATA_DIR}/system_ram.csv"
export_csv "${DISK_UTIL_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${DATA_DIR}/disk_util_mmcblk0.csv"
export_csv "${NET_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${DATA_DIR}/net_eth0.csv"

cp "${LOG_FILE}" "${RESULT_DIR}/redacted.log"

echo "=== run_${RUN_ID} DONE ==="
echo "START=$(epoch_to_kst "${START_EPOCH}") END=$(epoch_to_kst "${END_EPOCH}")"
echo "LOG_FILE=${LOG_FILE}"
echo "REQ_CSV=${REQ_CSV}"
echo "DATA_DIR=${DATA_DIR}"
