#!/bin/bash

# 설정
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/../.."
LOG_DIR="$PROJECT_ROOT/logs/redacted"
LOG_FILE="$LOG_DIR/step05_deployment_idle.log"

# 로그 디렉토리 확인
mkdir -p "$LOG_DIR"

echo "=== [Step 5] Deployment Idle (300s) Start ===" | tee -a "$LOG_FILE"

# 1. Nginx 배포가 실제로 떠 있는지 확인 (없으면 Idle 의미가 없음)
if ! kubectl get deployment nginx-deployment &> /dev/null; then
    echo "ERROR: nginx-deployment not found! Please run Step 4 first." | tee -a "$LOG_FILE"
    exit 1
fi

# 2. Idle 시작 시간 기록
START_TIME=$(date +%s%N)
echo "IDLE_START: $(date -d @${START_TIME:0:10} '+%Y-%m-%d %H:%M:%S.%N')" | tee -a "$LOG_FILE"

# 3. 300초 대기 (Netdata가 이 구간의 평온한 상태를 기록하도록 함)
echo "Waiting for 300 seconds (Cluster with Nginx)..."
sleep 300

# 4. Idle 종료 시간 기록
END_TIME=$(date +%s%N)
echo "IDLE_END: $(date -d @${END_TIME:0:10} '+%Y-%m-%d %H:%M:%S.%N')" | tee -a "$LOG_FILE"

echo "=== [Step 5] Deployment Idle Finished ===" | tee -a "$LOG_FILE"
