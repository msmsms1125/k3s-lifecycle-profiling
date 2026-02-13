import os
import sys
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec

STEP = "step12_apply_tinyllama_http"
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_BASE = os.path.join(BASE_DIR, "data", "netdata", STEP)
RESULT_BASE = os.path.join(BASE_DIR, "results", STEP)
LOG_BASE = os.path.join(BASE_DIR, "logs", "redacted", STEP)

def load_epoch(log_path, key):
    if not os.path.exists(log_path):
        return None
    with open(log_path) as f:
        for line in f:
            m = re.match(rf"^{key}=(\d+)", line.strip())
            if m:
                return int(m.group(1))
    return None

def load_cpu(csv_path):
    if not os.path.exists(csv_path):
        return None, None
    try:
        df = pd.read_csv(csv_path, comment="#")
        df.columns = [c.strip().strip('"') for c in df.columns]
        time_col = df.columns[0]
        df[time_col] = pd.to_numeric(df[time_col], errors="coerce")
        df = df.dropna(subset=[time_col])
        t = df[time_col].values
        numeric = df[df.columns[1:]].apply(pd.to_numeric, errors="coerce")
        idle_cols = [c for c in numeric.columns if "idle" in c.lower()]
        v = 100.0 - numeric[idle_cols[0]].values if idle_cols else numeric.sum(axis=1).values
        return t, v
    except Exception as e:
        print(f"  [WARN] load_cpu failed: {e}")
        return None, None

def load_ram(csv_path):
    if not os.path.exists(csv_path):
        return None, None
    try:
        df = pd.read_csv(csv_path, comment="#")
        df.columns = [c.strip().strip('"') for c in df.columns]
        time_col = df.columns[0]
        df[time_col] = pd.to_numeric(df[time_col], errors="coerce")
        df = df.dropna(subset=[time_col])
        t = df[time_col].values
        numeric = df[df.columns[1:]].apply(pd.to_numeric, errors="coerce")
        used_cols = [c for c in numeric.columns if "used" in c.lower()]
        v = numeric[used_cols[0]].abs().values if used_cols else numeric.iloc[:, 0].abs().values
        return t, v
    except Exception as e:
        print(f"  [WARN] load_ram failed: {e}")
        return None, None

def load_disk(csv_path):
    if not os.path.exists(csv_path):
        return None, None
    try:
        df = pd.read_csv(csv_path, comment="#")
        df.columns = [c.strip().strip('"') for c in df.columns]
        time_col = df.columns[0]
        df[time_col] = pd.to_numeric(df[time_col], errors="coerce")
        df = df.dropna(subset=[time_col])
        t = df[time_col].values
        numeric = df[df.columns[1:]].apply(pd.to_numeric, errors="coerce")
        if numeric.shape[1] == 0:
            return None, None
        v = pd.to_numeric(numeric.iloc[:, 0], errors="coerce").fillna(0).values
        return t, v
    except Exception as e:
        print(f"  [WARN] load_disk failed: {e}")
        return None, None

def load_net(csv_path):
    if not os.path.exists(csv_path):
        return None, None, None
    try:
        df = pd.read_csv(csv_path, comment="#")
        df.columns = [c.strip().strip('"') for c in df.columns]
        time_col = df.columns[0]
        df[time_col] = pd.to_numeric(df[time_col], errors="coerce")
        df = df.dropna(subset=[time_col])
        t = df[time_col].values
        numeric = df[df.columns[1:]].apply(pd.to_numeric, errors="coerce")
        rx_cols = [c for c in numeric.columns if any(k in c.lower() for k in ["received", "recv", "rx"])]
        tx_cols = [c for c in numeric.columns if any(k in c.lower() for k in ["sent", "tx"])]
        rx = numeric[rx_cols[0]].abs().values if rx_cols else numeric.iloc[:, 0].abs().values
        tx = numeric[tx_cols[0]].abs().values if tx_cols else (numeric.iloc[:, 1].abs().values if len(numeric.columns) > 1 else np.zeros_like(rx))
        return t, rx, tx
    except Exception as e:
        print(f"  [WARN] load_net failed: {e}")
        return None, None, None

def add_markers(ax, markers, y_top):
    for rel_t, label, color in markers:
        if rel_t is not None:
            ax.axvline(x=rel_t, color=color, linestyle="--", linewidth=0.9, alpha=0.85)
            ax.text(rel_t + 1, y_top * 0.95, label, color=color, fontsize=7, rotation=90, va="top")

def plot_run(run_id):
    data_dir = os.path.join(DATA_BASE, f"run_{run_id}")
    result_dir = os.path.join(RESULT_BASE, f"run_{run_id}")
    log_path = os.path.join(LOG_BASE, f"run_{run_id}.log")
    os.makedirs(result_dir, exist_ok=True)

    start  = load_epoch(log_path, "START_EPOCH")
    ready  = load_epoch(log_path, "READY_EPOCH")
    load_s = load_epoch(log_path, "LOAD_START_EPOCH")
    load_e = load_epoch(log_path, "LOAD_END_EPOCH")
    end    = load_epoch(log_path, "END_EPOCH")

    if start is None or end is None:
        print(f"[run_{run_id}] epoch missing in {log_path} — skip")
        return None

    t_cpu,  v_cpu  = load_cpu(os.path.join(data_dir, "system_cpu.csv"))
    t_ram,  v_ram  = load_ram(os.path.join(data_dir, "system_ram.csv"))
    t_disk, v_disk = load_disk(os.path.join(data_dir, "disk_util_mmcblk0.csv"))
    t_net,  v_rx,  v_tx = load_net(os.path.join(data_dir, "net_eth0.csv"))

    def rel(epoch):
        return (epoch - start) if epoch is not None else None

    markers = [
        (rel(start),  "START",  "black"),
        (rel(ready),  "READY",  "green"),
        (rel(load_s), "LOAD_S", "purple"),
        (rel(load_e), "LOAD_E", "darkorange"),
    ]

    fig = plt.figure(figsize=(14, 11))
    gs = GridSpec(4, 1, figure=fig, hspace=0.55)
    axes = [fig.add_subplot(gs[i]) for i in range(4)]

    panels = [
        (axes[0], t_cpu,  v_cpu,  "CPU Usage (%)",  "tab:blue"),
        (axes[1], t_ram,  v_ram,  "RAM Used (MB)",   "tab:orange"),
        (axes[2], t_disk, v_disk, "Disk Util (%)",   "tab:green"),
    ]
    for ax, t, v, ylabel, color in panels:
        ax.set_ylabel(ylabel, fontsize=9)
        if t is not None and v is not None:
            ax.plot(t - start, v, color=color, linewidth=1.2)
            top = np.nanmax(v) if len(v) > 0 else 1
            add_markers(ax, markers, top)
        ax.set_xlim(0, end - start)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=8)

    ax_net = axes[3]
    ax_net.set_ylabel("Network (KB/s)", fontsize=9)
    ax_net.set_xlabel("Time elapsed (s from START)", fontsize=9)
    if t_net is not None:
        rx_kb = v_rx / 1000.0
        tx_kb = v_tx / 1000.0
        ax_net.plot(t_net - start, rx_kb, color="tab:cyan", linewidth=1.2, label="Rx")
        ax_net.plot(t_net - start, tx_kb, color="tab:red",  linewidth=1.2, label="Tx")
        ax_net.legend(fontsize=8, loc="upper right")
        top = max(float(np.nanmax(rx_kb)) if len(rx_kb) > 0 else 0,
                  float(np.nanmax(tx_kb)) if len(tx_kb) > 0 else 0) or 1
        add_markers(ax_net, markers, top)
    ax_net.set_xlim(0, end - start)
    ax_net.grid(True, alpha=0.3)
    ax_net.tick_params(labelsize=8)

    t_ready_val = (ready - start) if ready else "N/A"
    fig.suptitle(
        f"[{STEP}]  run_{run_id}    T_ready={t_ready_val}s    T_total={end - start}s",
        fontsize=11, fontweight="bold", y=0.99
    )
    legend_patches = [mpatches.Patch(color=c, label=l) for _, l, c in markers]
    fig.legend(handles=legend_patches, loc="lower center", ncol=4, fontsize=8, bbox_to_anchor=(0.5, 0.0))

    out = os.path.join(result_dir, "fig1_timeseries.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[run_{run_id}] Fig1 → {out}")

    def safe_stat(t, v):
        if t is None or v is None or len(v) == 0:
            return np.nan, np.nan, np.nan
        v = np.array(v, dtype=float)
        v_clean = v[~np.isnan(v)]
        if len(v_clean) == 0:
            return np.nan, np.nan, np.nan
        return float(np.nanmean(v)), float(np.nanmax(v)), float(np.trapz(v, t))

    cpu_mean,  cpu_peak,  cpu_auc  = safe_stat(t_cpu,  v_cpu)
    ram_mean,  ram_peak,  ram_auc  = safe_stat(t_ram,  v_ram)
    disk_mean, disk_peak, disk_auc = safe_stat(t_disk, v_disk)
    def safe_peak(v, scale=1.0):
        if v is None or len(v) == 0:
            return np.nan
        v_clean = np.array(v, dtype=float)
        v_clean = v_clean[~np.isnan(v_clean)]
        return float(np.max(v_clean) / scale) if len(v_clean) > 0 else np.nan
    rx_peak = safe_peak(v_rx, 1000.0)
    tx_peak = safe_peak(v_tx, 1000.0)

    stats = dict(
        run=run_id,
        T_ready=(ready - start) if ready else np.nan,
        T_total=end - start,
        cpu_mean=cpu_mean, cpu_peak=cpu_peak, cpu_auc=cpu_auc,
        ram_mean=ram_mean, ram_peak=ram_peak, ram_auc=ram_auc,
        disk_mean=disk_mean, disk_peak=disk_peak, disk_auc=disk_auc,
        net_rx_peak_kbps=rx_peak, net_tx_peak_kbps=tx_peak,
    )
    pd.DataFrame([stats]).to_csv(os.path.join(result_dir, "stats.csv"), index=False)
    return stats

def main():
    runs = list(range(1, 11)) if len(sys.argv) == 1 else [int(x) for x in sys.argv[1:]]
    all_stats = [s for s in (plot_run(r) for r in runs) if s]
    if all_stats:
        df = pd.DataFrame(all_stats)
        out = os.path.join(RESULT_BASE, "summary.csv")
        os.makedirs(RESULT_BASE, exist_ok=True)
        df.to_csv(out, index=False)
        print(f"\nSummary → {out}")
        print(df[["run", "T_ready", "T_total", "cpu_peak", "ram_peak", "net_rx_peak_kbps"]].to_string(index=False))

if __name__ == "__main__":
    main()
