#!/usr/bin/env python3
import os
import re
import csv
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

# ==========================================
# 경로 설정
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(BASE_DIR, "logs/redacted/step08_cordon_uncordon.log")
OUT_DIR  = os.path.join(BASE_DIR, "results/step08_cordon_uncordon")
OUT_STATS_CSV = os.path.join(OUT_DIR, "step08_stats.csv")

# 타임스탬프 파싱 함수
def parse_timestamp(line):
    # 예: CORDON_START: 2026-01-21 22:00:00.123456
    parts = line.split(": ", 1)
    if len(parts) < 2: return None
    time_str = parts[1].strip()
    try:
        if "." in time_str:
            main, frac = time_str.split(".")
            time_str = f"{main}.{frac[:6]}"
        return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S.%f")
    except:
        return None

def main():
    if not os.path.exists(LOG_PATH):
        print(f"[ERROR] Log not found: {LOG_PATH}")
        return

    events = {}
    with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "CORDON_START:" in line: events["Cordon Start"] = parse_timestamp(line)
            if "SCALE_START:" in line: events["Scale Up (Pending)"] = parse_timestamp(line)
            if "UNCORDON_START:" in line: events["Uncordon Start"] = parse_timestamp(line)
            if "RECOVERY_END:" in line: events["All Running"] = parse_timestamp(line)

    if not events:
        print("[ERROR] No events found.")
        return
        
    os.makedirs(OUT_DIR, exist_ok=True)

    # CSV 저장
    with open(OUT_STATS_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["event", "timestamp"])
        for k, v in events.items():
            w.writerow([k, v])
    print(f"[INFO] Stats saved: {OUT_STATS_CSV}")

    # 간단한 타임라인 출력
    print("\n[Analysis Result]")
    sorted_events = sorted(events.items(), key=lambda x: x[1])
    start_time = sorted_events[0][1]
    
    for name, time in sorted_events:
        delta = (time - start_time).total_seconds()
        print(f"{name:<20}: +{delta:.2f}s")

if __name__ == "__main__":
    main()
