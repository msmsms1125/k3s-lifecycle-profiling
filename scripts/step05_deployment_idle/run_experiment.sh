#!/bin/bash

# 설정 (경로 문제 해결)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 프로젝트 루트: scripts/step05_deployment_idle (2단계 깊이) -> ../..
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
LOG_DIR="$PROJECT_ROOT/logs/redacted"
LOG_FILE="$LOG_DIR/step05_deployment_idle.log"

# 로그 폴더가 없으면 생성
mkdir -p "$LOG_DIR"

echo "=== [Step 5] Deployment Idle (300s) Start ===" | tee "$LOG_FILE"

# 1. Nginx 확인
if ! kubectl get deployment nginx-deployment &> /dev/null; then
    echo "[ERROR] nginx-deployment not found! Run Step 4 first." | tee -a "$LOG_FILE"
    exit 1
fi

# 2. 시작 시간
START_TIME=$(date +%s%N)
echo "IDLE_START: $(date -d @${START_TIME:0:10} '+%Y-%m-%d %H:%M:%S.%N')" | tee -a "$LOG_FILE"

# 3. 300초 대기
echo "Waiting for 300 seconds..."
sleep 300

# 4. 종료 시간
END_TIME=$(date +%s%N)
echo "IDLE_END: $(date -d @${END_TIME:0:10} '+%Y-%m-%d %H:%M:%S.%N')" | tee -a "$LOG_FILE"

echo "=== [Step 5] Finished ===" | tee -a "$LOG_FILE"
