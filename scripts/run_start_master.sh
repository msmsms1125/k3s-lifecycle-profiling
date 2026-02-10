# - master 노드에서 k3s 서비스를 start 하고, node Ready까지 대기하여 lifecycle timing 기록
# - Ready 이후 60초 안정화 관찰 후 종료 epoch 기록
#
# Artifacts:
# - logs/redacted/<RUN_ID>.log
#     start/ready/end 이벤트 로그 + epoch 기록
# - data/netdata/<RUN_ID>/
#
# Env variables:
# - RUN_ID는 내부 자동 생성(start_master_YYYYmmdd_HHMMSS)
# - timeout 값은 코드에 하드코딩(Ready wait: 300s, post-ready sleep: 60s)
#
# Epoch definition:
# - START_EPOCH : k3s start 직전(start_master_start)
# - READY_EPOCH : 노드 Ready 감지 직후(start_master_ready), rc=timeout 결과 포함
# - END_EPOCH   : READY 이후 60초 sleep 후(start_master_end)
set -euo pipefail

RUN_ID="start_master_$(date +%Y%m%d_%H%M%S)"
RUN_DIR="data/netdata/${RUN_ID}"
LOG="logs/redacted/${RUN_ID}.log"

mkdir -p "$RUN_DIR" logs/redacted results

START_EPOCH=$(date +%s)
echo "EVENT start_master_start $(date '+%F %T') (epoch=$START_EPOCH)" | tee "$LOG"

sudo systemctl start k3s

echo "WAIT: master Ready..." | tee -a "$LOG"
timeout 300 bash -c 'until sudo k3s kubectl get nodes 2>/dev/null | awk "NR>1{print \$2}" | grep -q Ready; do sleep 1; done'

READY_RC=$?
READY_EPOCH=$(date +%s)
echo "EVENT start_master_ready $(date '+%F %T') (epoch=$READY_EPOCH) rc=$READY_RC" | tee -a "$LOG"

sleep 60
END_EPOCH=$(date +%s)
echo "EVENT start_master_end $(date '+%F %T') (epoch=$END_EPOCH)" | tee -a "$LOG"

echo "RUN_ID=$RUN_ID"
echo "START_EPOCH=$START_EPOCH"
echo "READY_EPOCH=$READY_EPOCH"
echo "END_EPOCH=$END_EPOCH"
