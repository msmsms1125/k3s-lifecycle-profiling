#!/bin/bash
RUN_ID="stop_master_$(date +%Y%m%d_%H%M%S)"
mkdir -p logs/redacted

# (1) 시작 시간
START_EPOCH=$(date +%s)
echo "EVENT stop_master_start $(date '+%F %T') (epoch=$START_EPOCH)" | tee "logs/redacted/${RUN_ID}.log"

# (2) 종료 명령
echo "CMD: sudo systemctl stop k3s" | tee -a "logs/redacted/${RUN_ID}.log"
sudo systemctl stop k3s

# (3) 확인 (Inactive 될 때까지 대기)
timeout 60 bash -c 'until [ "$(systemctl is-active k3s)" == "inactive" ]; do sleep 1; done'

# (4) 완료 시간
READY_EPOCH=$(date +%s)
echo "EVENT stop_master_finish $(date '+%F %T') (epoch=$READY_EPOCH)" | tee -a "logs/redacted/${RUN_ID}.log"

# (5) 안정화 대기
echo "WAIT: Stabilizing resources (60s)..."
sleep 60

END_EPOCH=$(date +%s)
echo "EVENT stop_master_end $(date '+%F %T') (epoch=$END_EPOCH)" | tee -a "logs/redacted/${RUN_ID}.log"

echo "RUN_ID=$RUN_ID"
echo "DURATION=$((READY_EPOCH - START_EPOCH)) seconds"
