import argparse
import pandas as pd
import matplotlib.pyplot as plt
import os
import sys

# 1. 인자 받기
parser = argparse.ArgumentParser()
parser.add_argument('--log_file', type=str, required=True)
parser.add_argument('--output_dir', type=str, required=True)
args = parser.parse_args()

print(f"[Python] Analyzing Log: {args.log_file}")
print(f"[Python] Output Directory: {args.output_dir}")

# 2. 로그 파일 읽기 (예외 처리 추가)
try:
    # 여기에 실제 파싱 로직이 들어가야 하지만, 일단 파일이 열리는지만 확인
    with open(args.log_file, 'r') as f:
        log_content = f.read()
    print("[Python] Log file read successfully.")
except FileNotFoundError:
    print(f"[Python] Error: Log file not found at {args.log_file}")
    sys.exit(1)

# 3. 그래프 그리기 (데모용 더미 그래프)
# 실제 데이터 연동 전, 코드가 잘 도는지 확인하기 위한 가짜 플롯입니다.
plt.figure(figsize=(10, 6))
plt.title("Step 04: Deployment Resource Usage (Placeholder)")
plt.plot([0, 1, 2, 3], [10, 50, 20, 10], label='CPU Usage') # 가짜 데이터
plt.xlabel("Time")
plt.ylabel("Usage")
plt.legend()

# 4. 저장
os.makedirs(args.output_dir, exist_ok=True)
save_path = os.path.join(args.output_dir, "step04_plot.png")
plt.savefig(save_path)
print(f"[Python] Graph saved to {save_path}")
