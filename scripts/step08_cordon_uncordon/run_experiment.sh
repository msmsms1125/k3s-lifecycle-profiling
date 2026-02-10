# - step08_cordon_uncordon: 특정 worker 노드를 cordon/uncordon 하여 스케줄링을 제한/해제,
#   그 과정에서 발생하는 Pending/Running 전이와 자원 사용 패턴 측정
# - 1 run은 3개 세그먼트로 구성
#   - Seg A: cordon 이벤트 전후 WINDOW_SEC 관찰
#   - Seg B: replicas=3로 scale 후 Pending 관찰 (최대 PENDING_TIMEOUT)
#   - Seg C: uncordon 후 Pending들이 Running으로 전이되는 구간 관찰
#
# Artifacts (per run):
# - logs/redacted/step08_cordon_uncordon/run_<i>.log
#     segment별 START_EPOCH/READY_EPOCH/END_EPOCH 및 T_total 기록
# - data/netdata/step08_cordon_uncordon/run_<i>/
#     segA_cordon/  (A_AFTER..A_BEFORE 윈도우)
#       system_cpu.csv, system_ram.csv, disk_util_mmcblk0.csv, disk_io_mmcblk0.csv
#     segB_pending/ (B_START..B_END)
#       system_cpu.csv, system_ram.csv, disk_util_mmcblk0.csv, disk_io_mmcblk0.csv
#     segC_uncordon/ (C_START..C_END)
#       system_cpu.csv, system_ram.csv, disk_util_mmcblk0.csv, disk_io_mmcblk0.csv
# - results/step08_cordon_uncordon/
#     (analysis/plot_step08.py가 생성하는 산출물: fig/stats 등)
#
# Env variables:
# - RUNS            : 반복 횟수 (default: 10)
# - WORKER          : cordon/uncordon 대상 worker 노드명 (default: yhsensorpi)
# - DEPLOY          : 대상 deployment 이름 (default: nginx)
# - WINDOW_SEC      : cordon 전후 관찰 window 길이 (default: 60)
# - PENDING_TIMEOUT : Pending/Running 전이 관찰 최대 시간 (default: 300)
# - NETDATA_URL     : Netdata base URL (default: http://127.0.0.1:19999)
# - CPU_CHART       : CPU chart id (default: system.cpu)
# - RAM_CHART       : RAM chart id (default: system.ram)
# - DISK_UTIL_CHART : Disk util chart id (default: disk_util.mmcblk0)
# - IO_CHART        : IO chart id (default: system.io)
# - MANIFEST        : DEPLOY가 없을 때 apply할 manifest 경로
#                    (default: scripts/step04_apply_deployment/nginx-deployment.yaml)
#
# Epoch definition:
# - Segment A (cordon window)
#   - START_EPOCH = A_START (cordon 직전)
#   - END_EPOCH   = A_END   (cordon 직후)
#   - export range = [A_START-WINDOW_SEC, A_END+WINDOW_SEC]
# - Segment B (pending observation)
#   - START_EPOCH = B_START (scale --replicas=3 실행 시각)
#   - READY_EPOCH = B_READY (Pending이 "처음" 관찰된 시각; 없으면 빈칸)
#   - END_EPOCH   = B_END   (Running >= 3 도달 시각; 아니면 timeout 시각)
# - Segment C (uncordon transition)
#   - START_EPOCH = C_START (uncordon 실행 시각)
#   - END_EPOCH   = C_END   (Running >= 3 도달 시각; 아니면 timeout 시각)
# - T_total은 각 segment에서 (END_EPOCH - START_EPOCH)로 기록
set -euo pipefail

STEP="step08_cordon_uncordon"
RUNS="${RUNS:-10}"

WORKER="${WORKER:-yhsensorpi}"
DEPLOY="${DEPLOY:-nginx}"

WINDOW_SEC="${WINDOW_SEC:-60}"
PENDING_TIMEOUT="${PENDING_TIMEOUT:-300}"

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

  ######## Segment B: deploy/scale=3 시도 -> pending 관찰 ########
  # start = scale 실행 시각
  B_START="$(date +%s)"
  kubectl scale deploy/"${DEPLOY}" --replicas=3 >/dev/null

  B_READY=""
  end_deadline=$((B_START + PENDING_TIMEOUT))
  while (( $(date +%s) < end_deadline )); do
    if kubectl get pod -l app="${DEPLOY}" --no-headers 2>/dev/null | awk '$3=="Pending"{found=1} END{exit !found}'; then
      B_READY="$(date +%s)"
      break
    fi
    sleep 1
  done

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

  ######## Segment C: uncordon → pending Running ########
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
