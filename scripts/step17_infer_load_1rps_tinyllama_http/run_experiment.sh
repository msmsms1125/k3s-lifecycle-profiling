#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${1:-}"
if [[ -z "$RUN_ID" ]]; then
  echo "Usage: $0 <run_id>"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
STEP_NAME="$(basename "$SCRIPT_DIR")"

NS="${NS:-default}"
SERVICE_NAME="${SERVICE_NAME:-tinyllama-service}"

NETDATA_URL="${NETDATA_URL:-http://localhost:19999}"
NETDATA_GROUP_SEC="${NETDATA_GROUP_SEC:-5}"
NETDATA_CHART_CPU="${NETDATA_CHART_CPU:-system.cpu}"
NETDATA_CHART_RAM="${NETDATA_CHART_RAM:-system.ram}"
NETDATA_CHART_DISK_UTIL="${NETDATA_CHART_DISK_UTIL:-disk_util.mmcblk0}"
NETDATA_CHART_NET="${NETDATA_CHART_NET:-net.eth0}"

RPS="${RPS:-1}"
LOAD_DURATION_SEC="${LOAD_DURATION_SEC:-60}"
COOLDOWN_SEC="${COOLDOWN_SEC:-60}"
N_PREDICT="${N_PREDICT:-32}"
TEMPERATURE="${TEMPERATURE:-0.1}"
REQUEST_TIMEOUT_SEC="${REQUEST_TIMEOUT_SEC:-120}"

PROMPTS_FILE="${PROMPTS_FILE:-$SCRIPT_DIR/prompts_60.txt}"

if ! command -v jq >/dev/null 2>&1; then echo "ERROR: jq not found"; exit 1; fi
if ! command -v curl >/dev/null 2>&1; then echo "ERROR: curl not found"; exit 1; fi

LOG_DIR="$REPO_ROOT/logs/redacted/$STEP_NAME"
NETDATA_DIR="$REPO_ROOT/data/netdata/$STEP_NAME/run_${RUN_ID}"
mkdir -p "$LOG_DIR" "$NETDATA_DIR"

LOG_FILE="$LOG_DIR/run_${RUN_ID}.log"
REQ_CSV="$LOG_DIR/run_${RUN_ID}_requests.csv"

START_EPOCH="$(date +%s)"

SVC_JSON="$(kubectl -n "$NS" get svc "$SERVICE_NAME" -o json)"
NODEPORT="$(echo "$SVC_JSON" | jq -r '.spec.ports[0].nodePort')"
LABEL_SELECTOR="$(echo "$SVC_JSON" | jq -r '.spec.selector | to_entries | map("\(.key)=\(.value)") | join(",")')"

if [[ -z "${NODEPORT:-}" || "$NODEPORT" == "null" ]]; then
  echo "ERROR: nodePort not found for svc=$SERVICE_NAME ns=$NS"
  exit 1
fi
if [[ -z "${LABEL_SELECTOR:-}" || "$LABEL_SELECTOR" == "null" ]]; then
  echo "ERROR: selector not found for svc=$SERVICE_NAME ns=$NS"
  exit 1
fi

POD_NAME="$(kubectl -n "$NS" get pods -l "$LABEL_SELECTOR" -o json \
  | jq -r '.items[] | select(.status.containerStatuses != null) | select([.status.containerStatuses[].ready] | all) | .metadata.name' \
  | head -n 1)"
if [[ -z "${POD_NAME:-}" ]]; then
  echo "ERROR: no Ready pod found selector=$LABEL_SELECTOR"
  exit 1
fi

NODE_NAME="$(kubectl -n "$NS" get pod "$POD_NAME" -o jsonpath='{.spec.nodeName}')"
NODE_IP="$(kubectl get node "$NODE_NAME" -o json | jq -r '.status.addresses[] | select(.type=="InternalIP") | .address' | head -n 1)"
if [[ -z "${NODE_IP:-}" ]]; then
  echo "ERROR: InternalIP not found for node=$NODE_NAME"
  exit 1
fi

BASE_URL="http://${NODE_IP}:${NODEPORT}"

READY_CODE="$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/v1/models" || true)"
READY_CODE="${READY_CODE:-000}"
if [[ "$READY_CODE" != "200" ]]; then
  echo "ERROR: GET $BASE_URL/v1/models http_code=$READY_CODE"
  exit 2
fi
READY_EPOCH="$(date +%s)"

ENDPOINT_PATH="/v1/completions"

TEST_CODE="$(curl -s -o /dev/null -w "%{http_code}" \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Hello","max_tokens":1,"temperature":0.1,"stream":false}' \
  "$BASE_URL$ENDPOINT_PATH" || true)"
TEST_CODE="${TEST_CODE:-000}"
if [[ "$TEST_CODE" != 2* ]]; then
  echo "ERROR: POST $BASE_URL$ENDPOINT_PATH http_code=$TEST_CODE"
  exit 2
fi

LOAD_START_EPOCH="$(( $(date +%s) + 1 ))"

python3 "$SCRIPT_DIR/load_1rps.py" \
  --base-url "$BASE_URL" \
  --endpoint-path "$ENDPOINT_PATH" \
  --prompts-file "$PROMPTS_FILE" \
  --out-csv "$REQ_CSV" \
  --run-id "$RUN_ID" \
  --rps "$RPS" \
  --load-duration-sec "$LOAD_DURATION_SEC" \
  --load-start-epoch "$LOAD_START_EPOCH" \
  --n-predict "$N_PREDICT" \
  --temperature "$TEMPERATURE" \
  --request-timeout-sec "$REQUEST_TIMEOUT_SEC"

LOAD_END_EPOCH="$(date +%s)"
END_EPOCH="$(( LOAD_END_EPOCH + COOLDOWN_SEC ))"

{
  echo "STEP_NAME=$STEP_NAME"
  echo "RUN_ID=$RUN_ID"
  echo "NAMESPACE=$NS"
  echo "SERVICE_NAME=$SERVICE_NAME"
  echo "LABEL_SELECTOR=$LABEL_SELECTOR"
  echo "POD_NAME=$POD_NAME"
  echo "NODE_NAME=$NODE_NAME"
  echo "NODE_IP=$NODE_IP"
  echo "NODEPORT=$NODEPORT"
  echo "BASE_URL=$BASE_URL"
  echo "ENDPOINT_PATH=$ENDPOINT_PATH"
  echo "START_EPOCH=$START_EPOCH"
  echo "READY_EPOCH=$READY_EPOCH"
  echo "LOAD_START_EPOCH=$LOAD_START_EPOCH"
  echo "LOAD_END_EPOCH=$LOAD_END_EPOCH"
  echo "END_EPOCH=$END_EPOCH"
  echo "RPS=$RPS"
  echo "LOAD_DURATION_SEC=$LOAD_DURATION_SEC"
  echo "COOLDOWN_SEC=$COOLDOWN_SEC"
  echo "N_PREDICT=$N_PREDICT"
  echo "TEMPERATURE=$TEMPERATURE"
  echo "PROMPTS_FILE=$PROMPTS_FILE"
} > "$LOG_FILE"

NOW="$(date +%s)"
if (( NOW < END_EPOCH )); then
  sleep "$(( END_EPOCH - NOW ))"
fi

export_chart() {
  local chart="$1"
  local after="$2"
  local before="$3"
  local out="$4"
  local url="${NETDATA_URL%/}/api/v1/data"
  curl -sfG "$url" \
    --data-urlencode "chart=$chart" \
    --data-urlencode "after=$after" \
    --data-urlencode "before=$before" \
    --data-urlencode "format=csv" \
    --data-urlencode "group=average" \
    --data-urlencode "gtime=$NETDATA_GROUP_SEC" \
    > "$out"
}

export_chart "$NETDATA_CHART_CPU" "$START_EPOCH" "$END_EPOCH" "$NETDATA_DIR/system_cpu.csv" || true
export_chart "$NETDATA_CHART_RAM" "$START_EPOCH" "$END_EPOCH" "$NETDATA_DIR/system_ram.csv" || true
export_chart "$NETDATA_CHART_DISK_UTIL" "$START_EPOCH" "$END_EPOCH" "$NETDATA_DIR/disk_util_mmcblk0.csv" || true
export_chart "$NETDATA_CHART_NET" "$START_EPOCH" "$END_EPOCH" "$NETDATA_DIR/net_eth0.csv" || true

echo "DONE run=$RUN_ID"
