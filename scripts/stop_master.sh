# - master 노드에서 k3s 서비스를 stop 하고 inactive 상태가 될 때까지 대기하여 timing 기록
# - stop 완료 후 60초 안정화 관찰 후 종료 epoch 기록
#
# Artifacts:
# - logs/redacted/<RUN_ID>.log
#     stop start/finish/end 이벤트 로그 + epoch 기록
#
# Env variables:
# - RUN_ID는 내부 자동 생성(stop_master_YYYYmmdd_HHMMSS)
# - timeout 값은 코드에 하드코딩(inactive wait: 60s, post-finish sleep: 60s)
#
# Epoch definition:
# - START_EPOCH : stop 명령 직전(stop_master_start)
# - READY_EPOCH : k3s inactive 확인 직후(stop_master_finish)  <- READY=finish 의미
# - END_EPOCH   : READY 이후 60초 sleep 후(stop_master_end)
# - DURATION    : READY_EPOCH - START_EPOCH (로그 마지막에 출력)
RUN_ID="stop_master_$(date +%Y%m%d_%H%M%S)"
mkdir -p logs/redacted

# 시작 시간
START_EPOCH=$(date +%s)
echo "EVENT stop_master_start $(date '+%F %T') (epoch=$START_EPOCH)" | tee "logs/redacted/${RUN_ID}.log"

# 종료 명령
echo "CMD: sudo systemctl stop k3s" | tee -a "logs/redacted/${RUN_ID}.log"
sudo systemctl stop k3s

# Inactive 될 때까지 대기
timeout 60 bash -c 'until [ "$(systemctl is-active k3s)" == "inactive" ]; do sleep 1; done'

# 완료 시간
READY_EPOCH=$(date +%s)
echo "EVENT stop_master_finish $(date '+%F %T') (epoch=$READY_EPOCH)" | tee -a "logs/redacted/${RUN_ID}.log"

# 안정화 대기
echo "WAIT: Stabilizing resources (60s)..."
sleep 60

END_EPOCH=$(date +%s)
echo "EVENT stop_master_end $(date '+%F %T') (epoch=$END_EPOCH)" | tee -a "logs/redacted/${RUN_ID}.log"

echo "RUN_ID=$RUN_ID"
echo "DURATION=$((READY_EPOCH - START_EPOCH)) seconds"
