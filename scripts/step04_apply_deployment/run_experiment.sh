#!/bin/bash

# 경로 설정
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/../.."
LOG_DIR="$PROJECT_ROOT/logs/redacted"
YAML_FILE="$SCRIPT_DIR/nginx-deployment.yaml"
LOG_FILE="$LOG_DIR/step04_apply_deployment.log"
PYTHON_SCRIPT="$PROJECT_ROOT/analysis/plot_step04.py"
RESULT_DIR="$PROJECT_ROOT/results/step04_apply_deployment"

mkdir -p "$LOG_DIR"
mkdir -p "$RESULT_DIR"

echo "=== [Step 4] Apply Deployment Experiment Start ===" | tee -a "$LOG_FILE"

# 1. Start Timestamp
START_TIME=$(date +%s%N)
echo "DEPLOY_START: $(date -d @${START_TIME:0:10} '+%Y-%m-%d %H:%M:%S.%N')" | tee -a "$LOG_FILE"

# 2. Apply
kubectl apply -f "$YAML_FILE"

# 3. Wait
if ! kubectl rollout status deployment/nginx-deployment --timeout=300s; then
    echo "ERROR: Deployment failed!" | tee -a "$LOG_FILE"
    exit 1
fi

# 4. End Timestamp
END_TIME=$(date +%s%N)
echo "DEPLOY_END: $(date -d @${END_TIME:0:10} '+%Y-%m-%d %H:%M:%S.%N')" | tee -a "$LOG_FILE"

DURATION=$(( (END_TIME - START_TIME) / 1000000 ))
echo "Duration(ms): $DURATION" | tee -a "$LOG_FILE"

# 5. Idle (테스트를 위해 300초가 길면 10초로 줄여서 먼저 테스트해보세요)
echo "Waiting for stabilization (10s for test)..."
sleep 10
# 실전에서는 sleep 300 사용

# 6. Python Analysis 실행
echo "Running Python Analysis..." | tee -a "$LOG_FILE"
python3 "$PYTHON_SCRIPT" \
  --log_file "$LOG_FILE" \
  --output_dir "$RESULT_DIR"

echo "Done."
