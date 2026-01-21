#!/usr/bin/env python3
import os
import csv
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

# ==========================================
# 경로 설정
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(BASE_DIR, "results/step05_deployment_idle/step05_deployment_idle.log")
CSV_PATH = os.path.join(BASE_DIR, "netdata.csv")
OUT_DIR  = os.path.join(BASE_DIR, "results/step05_deployment_idle")

OUT_STATS_CSV = os.path.join(OUT_DIR, "step05_stats.csv")
OUT_GRAPH_PNG = os.path.join(OUT_DIR, "step05_idle_graph.png")

def parse_logs():
    """로그에서 IDLE 시작/종료 시간 추출"""
    if not os.path.exists(LOG_PATH):
        print(f"[ERROR] Log not found: {LOG_PATH}")
        return None, None

    start_time = None
    end_time = None

    with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "IDLE_START:" in line:
                # 2026-01-21 17:00:00.0000 -> 자르기
                t_str = line.split("IDLE_START:")[1].strip()
                if "." in t_str: t_str = t_str.split(".")[0] + "." + t_str.split(".")[1][:6]
                start_time = datetime.strptime(t_str, "%Y-%m-%d %H:%M:%S.%f")
            
            elif "IDLE_END:" in line:
                t_str = line.split("IDLE_END:")[1].strip()
                if "." in t_str: t_str = t_str.split(".")[0] + "." + t_str.split(".")[1][:6]
                end_time = datetime.strptime(t_str, "%Y-%m-%d %H:%M:%S.%f")

    return start_time, end_time

def analyze_and_plot(start, end):
    """CSV 데이터를 읽어서 통계 산출 및 그래프 그리기"""
    if not os.path.exists(CSV_PATH):
        print("[WARNING] 'netdata.csv' not found. Skipping analysis.")
        return

    try:
        df = pd.read_csv(CSV_PATH)
        df.columns = [c.strip().lower() for c in df.columns]
        df['time'] = pd.to_datetime(df['time'])

        # IDLE 구간 데이터만 필터링
        mask = (df['time'] >= start) & (df['time'] <= end)
        idle_df = df.loc[mask]

        if idle_df.empty:
            print("[WARNING] No data found in the IDLE time range.")
            return

        # 1. 통계 계산 (평균 CPU 등)
        data_col = df.columns[1] # 두 번째 컬럼(CPU 등) 사용
        avg_val = idle_df[data_col].mean()
        max_val = idle_df[data_col].max()
        
        print(f"[RESULT] Average {data_col}: {avg_val:.4f}")

        # 통계 저장
        with open(OUT_STATS_CSV, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["metric", "value"])
            w.writerow([f"avg_{data_col}", f"{avg_val:.4f}"])
            w.writerow([f"max_{data_col}", f"{max_val:.4f}"])
            w.writerow(["duration_sec", (end - start).total_seconds()])
        print(f"[INFO] Stats saved: {OUT_STATS_CSV}")

        # 2. 그래프 그리기
        plt.figure(figsize=(12, 6))
        plt.plot(df['time'], df[data_col], label=f"System {data_col}", color='#1f77b4', linewidth=1)
        
        # Idle 구간 강조 (초록색)
        plt.axvspan(start, end, color='green', alpha=0.15, label="Deployment Idle (300s)")
        plt.axvline(start, color='green', linestyle='--')
        plt.axvline(end, color='green', linestyle='--')

        plt.title(f"Step 5: Deployment Idle - Avg {data_col}: {avg_val:.2f}%")
        plt.xlabel("Time")
        plt.ylabel(f"Usage ({data_col})")
        plt.legend()
        plt.grid(True, linestyle='--', alpha=0.5)
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        plt.gcf().autofmt_xdate()
        
        plt.savefig(OUT_GRAPH_PNG)
        print(f"[INFO] Graph saved: {OUT_GRAPH_PNG}")

    except Exception as e:
        print(f"[ERROR] {e}")

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    start, end = parse_logs()
    
    if start and end:
        print(f"[INFO] Log Range: {start} ~ {end}")
        analyze_and_plot(start, end)
    else:
        print("[ERROR] Could not find start/end times in log.")

if __name__ == "__main__":
    main()
