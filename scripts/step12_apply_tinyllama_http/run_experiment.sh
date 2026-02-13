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

  curl -s \
    "http://${NETDATA_HOST}:${NETDATA_PORT}/api/v1/data?chart=${chart}&after=${after}&before=${before}&format=csv" \
    > "${out}"
}

kubectl delete deployment tinyllama-server --ignore-not-found=true
kubectl delete service tinyllama-service --ignore-not-found=true
sleep 10

START_EPOCH=$(date +%s)
echo "START_EPOCH=${START_EPOCH}" | tee "${LOG_FILE}"

kubectl apply -f "${YAML_DIR}/tinyllama-deployment.yaml" -f "${YAML_DIR}/tinyllama-service.yaml"

WORKER_IP=""
READY=0
TIMEOUT=300
ELAPSED=0

while [ "${ELAPSED}" -lt "${TIMEOUT}" ]; do
  sleep 5
  ELAPSED=$((ELAPSED + 5))

  POD_NAME=$(kubectl get pods -l app=tinyllama -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

  [ -z "${POD_NAME}" ] && continue

  WORKER_IP=$(kubectl get pod "${POD_NAME}" -o jsonpath='{.status.hostIP}' 2>/dev/null)

  [ -z "${WORKER_IP}" ] && continue

  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "http://${WORKER_IP}:30080/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d '{"model":"tinyllama","messages":[{"role":"user","content":"hi"}],"max_tokens":5}' \
    --connect-timeout 5 --max-time 30)

  if [ "${HTTP_CODE}" = "200" ]; then
    READY=1
    break
  fi
done

READY_EPOCH=$(date +%s)
echo "READY_EPOCH=${READY_EPOCH}" | tee -a "${LOG_FILE}"

LOAD_START_EPOCH=$(date +%s)
echo "LOAD_START_EPOCH=${LOAD_START_EPOCH}" | tee -a "${LOG_FILE}"

mapfile -t PROMPTS_ARR < "${PROMPTS}"

for PROMPT in "${PROMPTS_ARR[@]}"; do

  curl -s -o /dev/null \
    -X POST "http://${WORKER_IP}:30080/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"tinyllama\",\"messages\":[{\"role\":\"user\",\"content\":\"${PROMPT}\"}]}"

  sleep 1
done

LOAD_END_EPOCH=$(date +%s)
echo "LOAD_END_EPOCH=${LOAD_END_EPOCH}" | tee -a "${LOG_FILE}"

STABILIZE_REMAINING=$((START_EPOCH + 300 - $(date +%s)))

[ "${STABILIZE_REMAINING}" -gt 0 ] && sleep "${STABILIZE_REMAINING}"

END_EPOCH=$(date +%s)
echo "END_EPOCH=${END_EPOCH}" | tee -a "${LOG_FILE}"

fetch_csv "system.cpu" "${START_EPOCH}" "${END_EPOCH}" "${DATA_DIR}/system_cpu.csv"
fetch_csv "system.ram" "${START_EPOCH}" "${END_EPOCH}" "${DATA_DIR}/system_ram.csv"
fetch_csv "disk_util.mmcblk0" "${START_EPOCH}" "${END_EPOCH}" "${DATA_DIR}/disk_util_mmcblk0.csv"
fetch_csv "net.eth0" "${START_EPOCH}" "${END_EPOCH}" "${DATA_DIR}/net_eth0.csv"

cp "${LOG_FILE}" "${RESULT_DIR}/redacted.log"

echo "=== run_${RUN_ID} DONE ==="
