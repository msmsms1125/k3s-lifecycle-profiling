#!/usr/bin/env python3
import os
import re
import csv
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
from statistics import mean, pstdev

# ==========================================
# 경로 설정
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(BASE_DIR, "results/step04_apply_deployment/step04_apply_deployment.log")
CSV_PATH = os.path.join(BASE_DIR, "netdata.csv")
OUT_DIR  = os.path.join(BASE_DIR, "results/step04_apply_deployment")

# 결과 파일명
OUT_STATS_CSV = os.path.join(OUT_DIR, "step04_stats.csv")
OUT_GRAPH_PNG = os.path.join(OUT_DIR, "step04_resource_graph.png")

# 정규표현식
re_run_start = re.compile(r"Run\s*(\d+)_DEPLOY_START:\s*(.+)")
re_run_end   = re.compile(r"Run\s*(\d+)_DEPLOY_END:\s*(.+)")
re_run_dur   = re.compile(r"Run\s*(\d+)_Duration\(ms\):\s*(\d+)")

def parse_timestamp(time_str):
    """나노초(9자리)를 마이크로초(6자리)로 자르고 datetime 객체로 변환"""
    try:
        if "." in time_str:
            main_part, frac_part = time_str.split(".")
            # Python datetime은 6자리까지만 지원하므로 절삭
            time_str = f"{main_part}.{frac_part[:6]}"
        return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        return datetime.strptime(time_str.split(".")[0], "%Y-%m-%d %H:%M:%S")

def parse_logs():
    """로그 파일 파싱"""
    target_log = LOG_PATH
    if not os.path.exists(target_log):
        # logs/redacted 폴더 확인
        alt_path = os.path.join(BASE_DIR, "logs/redacted/step04_apply_deployment.log")
        if os.path.exists(alt_path):
            target_log = alt_path
        else:
            print(f"[ERROR] Log file not found at: {LOG_PATH}")
            return {}

    print(f"Reading Log: {target_log}")
    with open(target_log, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    runs = {}
    for line in lines:
        line = line.strip()
        
        m = re_run_start.search(line)
        if m:
            rid = int(m.group(1))
            runs.setdefault(rid, {})["start"] = parse_timestamp(m.group(2).strip())
            continue
        
        m = re_run_end.search(line)
        if m:
            rid = int(m.group(1))
            runs.setdefault(rid, {})["end"] = parse_timestamp(m.group(2).strip())
            continue

        m = re_run_dur.search(line)
        if m:
            rid = int(m.group(1))
            runs.setdefault(rid, {})["duration_ms"] = int(m.group(2))

    return runs

def save_stats(runs):
    """통계 저장"""
    if not runs:
        return

    run_rows = []
    durations = []
    
    for rid in sorted(runs.keys()):
        d = runs[rid]
        if "duration_ms" in d:
            run_rows.append([f"run_{rid}", d["duration_ms"]])
            durations.append(d["duration_ms"])

    with open(OUT_STATS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["label", "duration_ms"])
        w.writerows(run_rows)
        
        if durations:
            w.writerow([])
            w.writerow(["mean_ms", f"{mean(durations):.2f}"])
            if len(durations) > 1:
                w.writerow(["stdev_ms", f"{pstdev(durations):.2f}"])
            
    print(f"[INFO] Stats saved: {OUT_STATS_CSV}")

def plot_graph(runs):
    """그래프 그리기"""
    if not os.path.exists(CSV_PATH):
        print(f"[WARNING] 'netdata.csv' not found. Skipping graph generation.")
        return

    try:
        df = pd.read_csv(CSV_PATH)
        df.columns = [c.strip().lower() for c in df.columns]
        df['time'] = pd.to_datetime(df['time'])

        plt.figure(figsize=(12, 6))
        data_col = df.columns[1] 
        plt.plot(df['time'], df[data_col], label=f"System {data_col}")

        colors = ['red', 'green', 'orange']
        for rid, data in runs.items():
            if 'start' in data and 'end' in data:
                c = colors[(rid-1) % len(colors)]
                plt.axvspan(data['start'], data['end'], color=c, alpha=0.2, label=f"Run {rid}")

        plt.legend(loc='upper right')
        plt.gcf().autofmt_xdate()
        plt.savefig(OUT_GRAPH_PNG)
        print(f"[INFO] Graph saved: {OUT_GRAPH_PNG}")

    except Exception as e:
        print(f"[ERROR] Graph generation failed: {e}")

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    runs = parse_logs()
    if runs:
        save_stats(runs)
        plot_graph(runs)
    else:
        print("[ERROR] No valid run data found.")

if __name__ == "__main__":
    main()
