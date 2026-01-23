#!/usr/bin/env bash
set -euo pipefail

STEP="step08_cordon_uncordon"
RUNS="${RUNS:-10}"

WORKER="${WORKER:-yhsensorpi}"   # 워커 노드 이름 바꾸면 여기
DEPLOY="${DEPLOY:-nginx}"

WINDOW_SEC="${WINDOW_SEC:-60}"          # cordon 전후 관찰
PENDING_TIMEOUT="${PENDING_TIMEOUT:-300}" # pending 관찰 최대 시간

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="${REPO_ROOT}/logs/redacted/${STEP}"
DATA_DIR="${REPO_ROOT}/data/netdata/${STEP}"
RES_DIR="${REPO_ROOT}/results/${STEP}"

NETDATA_URL="${NETDATA_URL:-http://127.0.0.1:19999}"

CPU_CHART="${CPU_CHART:-system.cpu}"
RAM_CHART="${RAM_CHART:-system.ram}"
DISK_UTIL_CHART="${DISK_UTIL_CHART:-disk_util.mmcblk0}"
IO_CHART="${IO_CHART:-system.io}"

MANIFEST="${MANIFEST:-${REPO_ROOT}/scripts/step04_apply_deployment/nginx-deployment.yaml}"

mkdir -p "${LOG_DIR}" "${DATA_DIR}" "${RES_DIR}"

require_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "missing command: $1" >&2; exit 1; }; }
require_cmd date
require_cmd kubectl
require_cmd curl
require_cmd python3

calc_points() {
  local after="$1" before="$2"
  local dur=$((before - after))
  local p=$(( (dur + 4) / 5 ))
  if (( p < 2 )); then p=2; fi
  echo "${p}"
}

export_csv() {
  local chart="$1" after="$2" before="$3" out="$4"
  local points; points="$(calc_points "${after}" "${before}")"
  curl -sS -G "${NETDATA_URL}/api/v1/data" \
    --data-urlencode "chart=${chart}" \
    --data-urlencode "after=${after}" \
    --data-urlencode "before=${before}" \
    --data-urlencode "group=average" \
    --data-urlencode "points=${points}" \
    --data-urlencode "format=csv" \
    --data-urlencode "options=seconds,flip" \
    > "${out}"
}

wait_all_running_replicas() {
  local replicas="$1" timeout="$2"
  local end=$(( $(date +%s) + timeout ))
  while (( $(date +%s) < end )); do
    local running
    running="$(kubectl get pod -l app="${DEPLOY}" --no-headers 2>/dev/null \
      | awk '$3=="Running"{c++} END{print c+0}')"
    if [[ "${running}" -ge "${replicas}" ]]; then
      return 0
    fi
    sleep 1
  done
  return 1
}

# 준비: 노드 Ready, nginx 존재/롤아웃 정상, replicas=1로 시작(원하면 1로 고정)
prep() {
  kubectl wait --for=condition=Ready nodes --all --timeout=180s >/dev/null
  if ! kubectl get deploy/"${DEPLOY}" >/dev/null 2>&1; then
    [[ -f "${MANIFEST}" ]] && kubectl apply -f "${MANIFEST}" >/dev/null
  fi
  kubectl rollout status deploy/"${DEPLOY}" --timeout=300s >/dev/null
  kubectl scale deploy/"${DEPLOY}" --replicas=1 >/dev/null
  kubectl rollout status deploy/"${DEPLOY}" --timeout=300s >/dev/null
  kubectl uncordon "${WORKER}" >/dev/null 2>&1 || true
}

echo "[${STEP}] RUNS=${RUNS}, worker=${WORKER}, deploy=${DEPLOY}"
echo "[${STEP}] charts cpu=${CPU_CHART} ram=${RAM_CHART} disk_util=${DISK_UTIL_CHART} io=${IO_CHART}"

for i in $(seq 1 "${RUNS}"); do
  echo "== [${STEP}] run_${i}/${RUNS} =="

  prep

  RUN_LOG="${LOG_DIR}/run_${i}.log"
  RUN_DATA="${DATA_DIR}/run_${i}"
  mkdir -p "${RUN_DATA}"

  ######## Segment A: cordon (전후 60초씩 관찰) ########
  A_START="$(date +%s)"
  kubectl cordon "${WORKER}" >/dev/null
  A_END="$(date +%s)"
  A_AFTER=$((A_START - WINDOW_SEC))
  A_BEFORE=$((A_END + WINDOW_SEC))

  mkdir -p "${RUN_DATA}/segA_cordon"
  export_csv "${CPU_CHART}" "${A_AFTER}" "${A_BEFORE}" "${RUN_DATA}/segA_cordon/system_cpu.csv"
  export_csv "${RAM_CHART}" "${A_AFTER}" "${A_BEFORE}" "${RUN_DATA}/segA_cordon/system_ram.csv"
  export_csv "${DISK_UTIL_CHART}" "${A_AFTER}" "${A_BEFORE}" "${RUN_DATA}/segA_cordon/disk_util_mmcblk0.csv"
  export_csv "${IO_CHART}" "${A_AFTER}" "${A_BEFORE}" "${RUN_DATA}/segA_cordon/disk_io_mmcblk0.csv"

  ######## Segment B: deploy/scale=3 시도 → pending 관찰 ########
  # start = scale 실행 시각
  B_START="$(date +%s)"
  kubectl scale deploy/"${DEPLOY}" --replicas=3 >/dev/null

  # READY_EPOCH = Pending이 처음 관찰된 시각(없으면 빈칸)
  B_READY=""
  end_deadline=$((B_START + PENDING_TIMEOUT))
  while (( $(date +%s) < end_deadline )); do
    if kubectl get pod -l app="${DEPLOY}" --no-headers 2>/dev/null | awk '$3=="Pending"{found=1} END{exit !found}'; then
      B_READY="$(date +%s)"
      break
    fi
    sleep 1
  done

  # END_EPOCH = 모두 Running(>=3) 되는 시각(안되면 timeout 시각)
  if wait_all_running_replicas 3 "${PENDING_TIMEOUT}"; then
    B_END="$(date +%s)"
  else
    B_END="$(date +%s)"
  fi

  mkdir -p "${RUN_DATA}/segB_pending"
  export_csv "${CPU_CHART}" "${B_START}" "${B_END}" "${RUN_DATA}/segB_pending/system_cpu.csv"
  export_csv "${RAM_CHART}" "${B_START}" "${B_END}" "${RUN_DATA}/segB_pending/system_ram.csv"
  export_csv "${DISK_UTIL_CHART}" "${B_START}" "${B_END}" "${RUN_DATA}/segB_pending/disk_util_mmcblk0.csv"
  export_csv "${IO_CHART}" "${B_START}" "${B_END}" "${RUN_DATA}/segB_pending/disk_io_mmcblk0.csv"

  ######## Segment C: uncordon → pending들이 Running ########
  C_START="$(date +%s)"
  kubectl uncordon "${WORKER}" >/dev/null

  if wait_all_running_replicas 3 "${PENDING_TIMEOUT}"; then
    C_END="$(date +%s)"
  else
    C_END="$(date +%s)"
  fi

  mkdir -p "${RUN_DATA}/segC_uncordon"
  export_csv "${CPU_CHART}" "${C_START}" "${C_END}" "${RUN_DATA}/segC_uncordon/system_cpu.csv"
  export_csv "${RAM_CHART}" "${C_START}" "${C_END}" "${RUN_DATA}/segC_uncordon/system_ram.csv"
  export_csv "${DISK_UTIL_CHART}" "${C_START}" "${C_END}" "${RUN_DATA}/segC_uncordon/disk_util_mmcblk0.csv"
  export_csv "${IO_CHART}" "${C_START}" "${C_END}" "${RUN_DATA}/segC_uncordon/disk_io_mmcblk0.csv"

  ######## run log (네 포맷: START/READY/END + T_ready/T_total) ########
  # Step08은 구간 3개라서, 로그에 segment별로 찍어주자(파이썬이 summary로 합침)
  cat > "${RUN_LOG}" <<EOL
STEP=${STEP}
RUN=${i}

SEG_A=cordon
START_EPOCH=${A_START}
READY_EPOCH=
END_EPOCH=${A_END}
T_ready=
T_total=$((A_END - A_START))

SEG_B=pending
START_EPOCH=${B_START}
READY_EPOCH=${B_READY}
END_EPOCH=${B_END}
T_ready=$([[ -n "${B_READY}" ]] && echo $((B_READY - B_START)) || echo "")
T_total=$((B_END - B_START))

SEG_C=uncordon
START_EPOCH=${C_START}
READY_EPOCH=
END_EPOCH=${C_END}
T_ready=
T_total=$((C_END - C_START))
EOL

done

python3 "${REPO_ROOT}/analysis/plot_step08.py" --step "${STEP}"
echo "[DONE] ${STEP}"
