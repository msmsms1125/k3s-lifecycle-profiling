#!/usr/bin/env python3
import os
import re
import csv
import matplotlib.pyplot as plt
import numpy as np

# ==========================================
# 경로 설정
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(BASE_DIR, "logs/redacted/step07_rollout_restart.log")
OUT_DIR  = os.path.join(BASE_DIR, "results/step07_rollout_restart")
OUT_GRAPH_PNG = os.path.join(OUT_DIR, "step07_rollout_duration.png")
OUT_STATS_CSV = os.path.join(OUT_DIR, "step07_stats.csv")

# 정규표현식
re_dur = re.compile(r"Run\s*(\d+)_Duration\(ms\):\s*(\d+)")

def parse_logs():
    if not os.path.exists(LOG_PATH):
        print(f"[ERROR] Log not found: {LOG_PATH}")
        return {}
    
    runs = {}
    with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            m = re_dur.search(line)
            if m:
                runs[int(m.group(1))] = int(m.group(2))
    return runs

def save_stats(runs):
    with open(OUT_STATS_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["run", "duration_ms"])
        for r in sorted(runs.keys()):
            w.writerow([f"Run {r}", runs[r]])
    print(f"[INFO] Stats saved: {OUT_STATS_CSV}")

def plot_graph(runs):
    if not runs: return

    rids = sorted(runs.keys())
    times = [runs[r] for r in rids]
    
    # 그래프 그리기
    plt.figure(figsize=(10, 6))
    bars = plt.bar(rids, times, color='#9B59B6', edgecolor='black', alpha=0.8, width=0.5)
    
    plt.xlabel('Test Runs', fontsize=12, fontweight='bold')
    plt.ylabel('Duration (ms)', fontsize=12, fontweight='bold')
    plt.title('Step 7: Rollout Restart Duration (3 Replicas)', fontsize=14, fontweight='bold', pad=20)
    plt.xticks(rids, [f"Run {r}" for r in rids])
    plt.grid(axis='y', linestyle='--', alpha=0.5)
    
    # 값 표시
    for rect in bars:
        height = rect.get_height()
        plt.text(rect.get_x() + rect.get_width()/2.0, height, f'{height}', ha='center', va='bottom', fontweight='bold')

    plt.tight_layout()
    plt.savefig(OUT_GRAPH_PNG, dpi=300)
    print(f"[INFO] Graph saved: {OUT_GRAPH_PNG}")

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    runs = parse_logs()
    if runs:
        save_stats(runs)
        plot_graph(runs)
    else:
        print("[ERROR] No run data found.")

if __name__ == "__main__":
    main()
