#!/usr/bin/env python3
import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

# ==========================================
# 설정
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(BASE_DIR, "logs/redacted/step08_cordon_uncordon.log")
OUT_DIR  = os.path.join(BASE_DIR, "results/step08_cordon_uncordon")

# Netdata CSV 파일들 (프로젝트 루트에 위치)
CPU_CSV  = os.path.join(BASE_DIR, "cpu.csv")
MEM_CSV  = os.path.join(BASE_DIR, "mem.csv")
DISK_CSV = os.path.join(BASE_DIR, "disk.csv")

OUT_GRAPH_PNG = os.path.join(OUT_DIR, "step08_resource_graph.png")

def parse_logs():
    if not os.path.exists(LOG_PATH):
        print(f"[ERROR] Log not found: {LOG_PATH}")
        return {}

    events = {}
    with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if ": " in line:
                key, time_str = line.split(": ", 1)
                try:
                    if "." in time_str:
                        main, frac = time_str.strip().split(".")
                        time_str = f"{main}.{frac[:6]}"
                    t = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S.%f")
                    
                    if "CORDON_START" in key: events["Cordon Start"] = t
                    if "SCALE_START" in key:  events["Scale Up (Pending)"] = t
                    if "UNCORDON_START" in key: events["Uncordon Start"] = t
                    if "RECOVERY_END" in key: events["Recovery End"] = t
                except:
                    continue
    return events

def load_and_prep_csv(filepath, event_date):
    if not os.path.exists(filepath):
        print(f"[WARNING] File not found: {filepath}")
        return None
    try:
        df = pd.read_csv(filepath)
        df.columns = [c.strip().lower() for c in df.columns]
        # 날짜가 없고 시간만 있는 경우, 실험 날짜를 붙여줌
        df['time'] = df['timestamp'].apply(lambda x: pd.to_datetime(f"{event_date} {x}"))
        return df
    except Exception as e:
        print(f"[ERROR] Failed to read {filepath}: {e}")
        return None

def plot_graph(events):
    if not events: 
        print("[ERROR] No events found in log.")
        return

    exp_date = list(events.values())[0].date()
    
    df_cpu  = load_and_prep_csv(CPU_CSV, exp_date)
    df_mem  = load_and_prep_csv(MEM_CSV, exp_date)
    df_disk = load_and_prep_csv(DISK_CSV, exp_date)

    if df_cpu is None and df_mem is None and df_disk is None:
        print("[ERROR] No CSV data found. Please place cpu.csv, mem.csv, disk.csv in project root.")
        return

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
    
    # 1. CPU
    if df_cpu is not None:
        cols = [c for c in df_cpu.columns if c not in ['time', 'timestamp', 'anomaly%', 'annotations']]
        axes[0].stackplot(df_cpu['time'], [df_cpu[c] for c in cols], labels=cols, alpha=0.7)
        axes[0].set_title("Step 8: CPU Utilization")
        axes[0].set_ylabel("%")
        axes[0].legend(loc='upper right', fontsize='small')

    # 2. Memory
    if df_mem is not None:
        col = next((c for c in df_mem.columns if 'avail' in c or 'free' in c), None)
        if col:
            axes[1].plot(df_mem['time'], df_mem[col], color='green')
            axes[1].set_title("Step 8: Available Memory")
            axes[1].set_ylabel("GiB/MB")

    # 3. Disk
    if df_disk is not None:
        cols = [c for c in df_disk.columns if c not in ['time', 'timestamp', 'anomaly%', 'annotations']]
        for c in cols:
            axes[2].plot(df_disk['time'], df_disk[c], label=c)
        axes[2].set_title("Step 8: Disk I/O")
        axes[2].set_ylabel("KB/s")
        axes[2].legend()

    # 이벤트 표시
    colors = {"Cordon Start": "gray", "Scale Up (Pending)": "orange", 
              "Uncordon Start": "blue", "Recovery End": "green"}
    
    start_t = events["Cordon Start"]
    end_t = events["Recovery End"]
    # 그래프 범위 설정 (앞뒤 여유)
    axes[0].set_xlim(start_t - pd.Timedelta(seconds=10), end_t + pd.Timedelta(seconds=30))

    for ax in axes:
        ax.grid(True, linestyle='--', alpha=0.5)
        for name, t in events.items():
            c = colors.get(name, 'black')
            ax.axvline(t, color=c, linestyle='--', linewidth=1.5)
            if ax == axes[0]:
                ax.text(t, ax.get_ylim()[1], name, rotation=45, color=c, va='bottom', fontweight='bold')
    
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
    plt.tight_layout()
    plt.savefig(OUT_GRAPH_PNG)
    print(f"[INFO] Graph saved: {OUT_GRAPH_PNG}")

if __name__ == "__main__":
    plot_graph(parse_logs())
