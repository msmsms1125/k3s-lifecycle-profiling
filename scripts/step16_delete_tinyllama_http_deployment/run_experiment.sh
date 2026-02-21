#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${1:-}"
if [[ -z "${RUN_ID}" ]]; then
  echo "usage: $0 <run_id>"
  exit 1
fi

STEP="step16_delete_tinyllama_http_deployment"
NS="${NS:-default}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

SCRIPTS_DIR="${REPO_ROOT}/scripts"
LOG_DIR="${REPO_ROOT}/logs/redacted/${STEP}"
DATA_DIR="${REPO_ROOT}/data/netdata/${STEP}/run_${RUN_ID}"
RESULT_DIR="${REPO_ROOT}/results/${STEP}/run_${RUN_ID}"

mkdir -p "${LOG_DIR}" "${DATA_DIR}" "${RESULT_DIR}"

RUN_LOG="${LOG_DIR}/run_${RUN_ID}.log"
exec > >(tee -a "${RUN_LOG}") 2>&1

DEPLOY_YAML="${DEPLOY_YAML:-${SCRIPTS_DIR}/step12_apply_tinyllama_http/tinyllama-deployment.yaml}"
SVC_YAML="${SVC_YAML:-${SCRIPTS_DIR}/step12_apply_tinyllama_http/tinyllama-service.yaml}"

NETDATA_HOST="${NETDATA_HOST:-127.0.0.1}"
NETDATA_PORT="${NETDATA_PORT:-19999}"
NETDATA_GTIME="${NETDATA_GTIME:-5}"

NET_IFACE="${NET_IFACE:-eth0}"
DISK_DEV="${DISK_DEV:-mmcblk0}"

echo "STEP=${STEP}"
echo "RUN_ID=${RUN_ID}"
echo "NS=${NS}"
echo "DEPLOY_YAML=${DEPLOY_YAML}"
echo "SVC_YAML=${SVC_YAML}"
date -Is

echo "=== PREP: apply service/deployment ==="
kubectl apply -n "${NS}" -f "${SVC_YAML}"
kubectl apply -n "${NS}" -f "${DEPLOY_YAML}"

DEPLOY_RES="$(kubectl get -n "${NS}" -f "${DEPLOY_YAML}" -o name | head -n 1 || true)"
SVC_RES="$(kubectl get -n "${NS}" -f "${SVC_YAML}" -o name | head -n 1 || true)"

echo "DEPLOY_RES=${DEPLOY_RES}"
echo "SVC_RES=${SVC_RES}"

if [[ -z "${DEPLOY_RES}" ]]; then
  echo "DEPLOY_RES 확인되지 않음 (kubectl get -f 실패)"
  exit 1
fi
if [[ -z "${SVC_RES}" ]]; then
  echo "SVC_RES 확인되지 않음 (kubectl get -f 실패)"
  exit 1
fi

echo "=== WAIT: rollout ready ==="
kubectl rollout status -n "${NS}" "${DEPLOY_RES}" --timeout=600s
READY_EPOCH="$(date +%s)"
echo "READY_EPOCH=${READY_EPOCH}"

echo "=== SELECTOR: derive from deployment.spec.selector.matchLabels (no hardcoded app=...) ==="
SELECTOR="$(kubectl get -n "${NS}" "${DEPLOY_RES}" -o json | python3 - <<'PY'
import sys, json
d = json.load(sys.stdin)
ml = d.get("spec", {}).get("selector", {}).get("matchLabels", {})
print(",".join([f"{k}={v}" for k,v in ml.items()]))
PY
)"
echo "SELECTOR=${SELECTOR}"

readarray -t PODS_BEFORE < <(kubectl get pods -n "${NS}" -l "${SELECTOR}" -o name 2>/dev/null || true)
echo "PODS_BEFORE_COUNT=${#PODS_BEFORE[@]}"
if ((${#PODS_BEFORE[@]} > 0)); then
  printf "%s\n" "${PODS_BEFORE[@]}"
fi

echo "=== HTTP CHECK: service clusterIP:port (inference ready) ==="
SVC_IP="$(kubectl get -n "${NS}" "${SVC_RES}" -o jsonpath='{.spec.clusterIP}' 2>/dev/null || true)"
SVC_PORT="$(kubectl get -n "${NS}" "${SVC_RES}" -o jsonpath='{.spec.ports[0].port}' 2>/dev/null || true)"
HEALTH_PATH="${HEALTH_PATH:-/}"
if [[ -n "${SVC_IP}" && "${SVC_IP}" != "None" && -n "${SVC_PORT}" ]]; then
  URL="http://${SVC_IP}:${SVC_PORT}${HEALTH_PATH}"
  HTTP_CODE="$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "${URL}" || echo "curl_failed")"
  echo "HTTP_CHECK_URL=${URL}"
  echo "HTTP_CODE=${HTTP_CODE}"
else
  echo "HTTP_CHECK_SKIPPED (SVC_IP or SVC_PORT 확인되지 않음)"
fi

echo "=== DELETE: START_EPOCH at delete command ==="
START_EPOCH="$(date +%s)"
echo "START_EPOCH=${START_EPOCH}"
kubectl delete -n "${NS}" -f "${DEPLOY_YAML}" --ignore-not-found=true

echo "=== WAIT: pods delete complete (based on actual pods list) ==="
if ((${#PODS_BEFORE[@]} > 0)); then
  kubectl wait -n "${NS}" --for=delete "${PODS_BEFORE[@]}" --timeout=600s || true
fi

echo "=== WAIT: deployment delete complete ==="
kubectl wait -n "${NS}" --for=delete "${DEPLOY_RES}" --timeout=600s || true
DELETE_COMPLETE_EPOCH="$(date +%s)"
echo "DELETE_COMPLETE_EPOCH=${DELETE_COMPLETE_EPOCH}"

END_EPOCH="$((DELETE_COMPLETE_EPOCH + 60))"
echo "END_EPOCH=${END_EPOCH}"

echo "=== ORPHAN PROCESS CHECK (grep) ==="
ps aux | grep -E 'llama|tinyllama|server\.py' | head -n 50 || true

echo "=== COOL-DOWN: sleep until END_EPOCH ==="
NOW="$(date +%s)"
if (( END_EPOCH > NOW )); then
  sleep "$((END_EPOCH - NOW))"
fi

echo "=== NETDATA EXPORT CSV (after=START, before=END, gtime=${NETDATA_GTIME}s avg) ==="
AFTER="${START_EPOCH}"
BEFORE="${END_EPOCH}"
echo "EXPORT_AFTER=${AFTER}"
echo "EXPORT_BEFORE=${BEFORE}"

netdata_export() {
  local chart="$1"
  local outfile="$2"
  local url="http://${NETDATA_HOST}:${NETDATA_PORT}/api/v1/data?chart=${chart}&after=${AFTER}&before=${BEFORE}&format=csv&group=average&gtime=${NETDATA_GTIME}"
  local code
  code="$(curl -s -w "%{http_code}" -o "${outfile}" "${url}" || true)"
  if [[ "${code}" != "200" ]]; then
    rm -f "${outfile}" || true
    echo "NETDATA_EXPORT_FAIL chart=${chart} http_code=${code}"
    return 1
  fi
  echo "NETDATA_EXPORT_OK chart=${chart} -> ${outfile}"
  return 0
}

netdata_export "system.cpu" "${DATA_DIR}/system_cpu.csv"
netdata_export "system.ram" "${DATA_DIR}/system_ram.csv"
netdata_export "disk_util.${DISK_DEV}" "${DATA_DIR}/disk_util_${DISK_DEV}.csv"
netdata_export "net.${NET_IFACE}" "${DATA_DIR}/net_${NET_IFACE}.csv"

netdata_export "disk_io.${DISK_DEV}" "${DATA_DIR}/disk_io_${DISK_DEV}.csv" || true

echo "=== PLOT RUN (Fig1 + stats.csv) ==="
python3 "${REPO_ROOT}/analysis/plot_step16_tinyllama_delete_deployment.py" --step "${STEP}" --run "${RUN_ID}"

echo "=== COPY LOG TO results/<step>/run_<i>/redacted.log ==="
cp -f "${RUN_LOG}" "${RESULT_DIR}/redacted.log"

echo "DONE"
