import os
import sys
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

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


def _read_csv_with_time(csv_path):
    if not os.path.exists(csv_path):
        return None, None

    try:
        df = pd.read_csv(csv_path, comment="#")
    except pd.errors.EmptyDataError:
        return None, None

    df.columns = [c.strip().strip('"') for c in df.columns]
    time_col = df.columns[0]

    s = df[time_col].astype(str)
    df[time_col] = pd.to_numeric(s, errors="coerce")

    if df[time_col].isna().all():
        dt = pd.to_datetime(s, errors="coerce")
        df[time_col] = dt.astype("int64") / 1e9

    df = df.dropna(subset=[time_col])
    if df.empty:
        return None, None

    df = df.sort_values(by=time_col)

    t = df[time_col].values.astype(float)

    if len(t) > 0 and np.nanmedian(t) > 1e12:
        t = t / 1000.0

    return df, t


def load_cpu(csv_path):
    try:
        df, t = _read_csv_with_time(csv_path)
        if df is None:
            return None, None
        numeric = df[df.columns[1:]].apply(pd.to_numeric, errors="coerce")
        if numeric.shape[1] == 0:
            return None, None
        idle_cols = [c for c in numeric.columns if "idle" in c.lower()]
        v = (100.0 - numeric[idle_cols[0]].values) if idle_cols else numeric.sum(axis=1).values
        return t, v.astype(float)
    except Exception as e:
        print(f"  [WARN] load_cpu failed: {e}")
        return None, None


def load_ram(csv_path):
    try:
        df, t = _read_csv_with_time(csv_path)
        if df is None:
            return None, None
        numeric = df[df.columns[1:]].apply(pd.to_numeric, errors="coerce")
        if numeric.shape[1] == 0:
            return None, None
        used_cols = [c for c in numeric.columns if "used" in c.lower()]
        v = numeric[used_cols[0]].abs().values if used_cols else numeric.iloc[:, 0].abs().values
        return t, v.astype(float)
    except Exception as e:
        print(f"  [WARN] load_ram failed: {e}")
        return None, None


def load_disk(csv_path):
    try:
        df, t = _read_csv_with_time(csv_path)
        if df is None:
            return None, None
        numeric = df[df.columns[1:]].apply(pd.to_numeric, errors="coerce")
        if numeric.shape[1] == 0:
            return None, None
        v = pd.to_numeric(numeric.iloc[:, 0], errors="coerce").fillna(0).values
        return t, v.astype(float)
    except Exception as e:
        print(f"  [WARN] load_disk failed: {e}")
        return None, None


def load_net(csv_path):
    try:
        df, t = _read_csv_with_time(csv_path)
        if df is None:
            return None, None, None
        numeric = df[df.columns[1:]].apply(pd.to_numeric, errors="coerce")
        if numeric.shape[1] == 0:
            return None, None, None

        rx_cols = [c for c in numeric.columns if any(k in c.lower() for k in ["received", "recv", "rx"])]
        tx_cols = [c for c in numeric.columns if any(k in c.lower() for k in ["sent", "tx"])]

        rx = numeric[rx_cols[0]].abs().values if rx_cols else numeric.iloc[:, 0].abs().values
        if tx_cols:
            tx = numeric[tx_cols[0]].abs().values
        else:
            tx = numeric.iloc[:, 1].abs().values if len(numeric.columns) > 1 else np.zeros_like(rx)

        return t, rx.astype(float), tx.astype(float)
    except Exception as e:
        print(f"  [WARN] load_net failed: {e}")
        return None, None, None


def add_markers(ax, markers, y_top):
    for rel_t, label, color in markers:
        if rel_t is not None:
            ax.axvline(x=rel_t, color=color, linestyle="--", linewidth=0.9, alpha=0.85)
            ax.text(rel_t + 1, y_top * 0.95, label, color=color, fontsize=7, rotation=90, va="top")


def safe_stat(t, v):
    if t is None or v is None:
        return np.nan, np.nan, np.nan
    if len(v) == 0 or np.all(np.isnan(v)):
        return np.nan, np.nan, np.nan
    try:
        auc = float(np.trapz(v, t)) if (len(t) == len(v) and len(t) > 1) else np.nan
        auc = abs(auc)
    except Exception:
        auc = np.nan
    return float(np.nanmean(v)), float(np.nanmax(v)), auc


def align_time(t, start_epoch):
    """
    [FIX 2] Timezone Correction
    If the CSV timestamps (t) are wildly different from START_EPOCH (e.g. > 1 hour),
    calculate the offset (rounded to nearest hour) and shift t to align.
    """
    if t is None or len(t) == 0:
        return t
    
    diff = t[0] - float(start_epoch)
    if abs(diff) > 3000:
        # Round to nearest hour (3600s)
        hours_off = round(diff / 3600.0)
        offset = hours_off * 3600.0
        print(f"    [INFO] Detected timezone offset {hours_off}h ({offset}s). Aligning data.")
        return t - offset
    return t


def plot_run(run_id):
    data_dir = os.path.join(DATA_BASE, f"run_{run_id}")
    result_dir = os.path.join(RESULT_BASE, f"run_{run_id}")
    log_path = os.path.join(LOG_BASE, f"run_{run_id}.log")
    os.makedirs(result_dir, exist_ok=True)

    start = load_epoch(log_path, "START_EPOCH")
    ready = load_epoch(log_path, "READY_EPOCH")
    load_s = load_epoch(log_path, "LOAD_START_EPOCH")
    load_e = load_epoch(log_path, "LOAD_END_EPOCH")
    end = load_epoch(log_path, "END_EPOCH")

    if start is None or end is None:
        print(f"[run_{run_id}] epoch missing in {log_path} — skip")
        return None

    t_cpu, v_cpu = load_cpu(os.path.join(data_dir, "system_cpu.csv"))
    t_ram, v_ram = load_ram(os.path.join(data_dir, "system_ram.csv"))
    t_disk, v_disk = load_disk(os.path.join(data_dir, "disk_util_mmcblk0.csv"))
    t_net, v_rx, v_tx = load_net(os.path.join(data_dir, "net_eth0.csv"))

    t_cpu = align_time(t_cpu, start)
    t_ram = align_time(t_ram, start)
    t_disk = align_time(t_disk, start)
    t_net = align_time(t_net, start)

    def rel(epoch):
        return (epoch - start) if epoch is not None else None

    markers = [
        (0, "START", "black"),
        (rel(ready), "READY", "green"),
        (rel(load_s), "LOAD_S", "purple"),
        (rel(load_e), "LOAD_E", "darkorange"),
    ]

    fig = plt.figure(figsize=(14, 11))
    gs = GridSpec(4, 1, figure=fig, hspace=0.55)
    axes = [fig.add_subplot(gs[i]) for i in range(4)]

    panels = [
        (axes[0], t_cpu, v_cpu, "CPU Usage (%)", "tab:blue"),
        (axes[1], t_ram, v_ram, "RAM Used (MB)", "tab:orange"),
        (axes[2], t_disk, v_disk, "Disk Util (%)", "tab:green"),
    ]

    for ax, t, v, ylabel, color in panels:
        ax.set_ylabel(ylabel, fontsize=9)
        if t is not None and v is not None and len(t) > 0 and len(v) > 0:
            x = t - float(start)
            mask = (x >= -5) & (x <= (end - start + 5))
            x2 = x[mask]
            v2 = v[mask]
            if len(x2) > 0 and len(v2) > 0:
                ax.plot(x2, v2, color=color, linewidth=1.2)
                top = float(np.nanmax(v2)) if not np.all(np.isnan(v2)) else 1.0
                add_markers(ax, markers, top)
            else:
                print(f"    [DEBUG] Empty plot for {ylabel}. t range: {t[0]-start:.1f} to {t[-1]-start:.1f}")

        ax.set_xlim(0, end - start)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=8)

    ax_net = axes[3]
    ax_net.set_ylabel("Network (KB/s)", fontsize=9)
    ax_net.set_xlabel("Time elapsed (s from START)", fontsize=9)

    if t_net is not None and v_rx is not None and v_tx is not None and len(t_net) > 0:
        x = t_net - float(start)
        mask = (x >= -5) & (x <= (end - start + 5))
        x2 = x[mask]
        rx_kb = (v_rx / 1000.0)[mask]
        tx_kb = (v_tx / 1000.0)[mask]

        if len(x2) > 0:
            ax_net.plot(x2, rx_kb, color="tab:cyan", linewidth=1.2, label="Rx")
            ax_net.plot(x2, tx_kb, color="tab:red", linewidth=1.2, label="Tx")
            ax_net.legend(fontsize=8, loc="upper right")

            top = 1.0
            if rx_kb.size > 0 and not np.all(np.isnan(rx_kb)):
                top = max(top, float(np.nanmax(rx_kb)))
            if tx_kb.size > 0 and not np.all(np.isnan(tx_kb)):
                top = max(top, float(np.nanmax(tx_kb)))
            add_markers(ax_net, markers, top)
        else:
             print(f"    [DEBUG] Empty plot for Network. t range: {t_net[0]-start:.1f} to {t_net[-1]-start:.1f}")

    ax_net.set_xlim(0, end - start)
    ax_net.grid(True, alpha=0.3)
    ax_net.tick_params(labelsize=8)

    t_ready_val = (ready - start) if ready else np.nan
    fig.suptitle(
        f"[{STEP}]  run_{run_id}    T_ready={t_ready_val}s    T_total={end - start}s",
        fontsize=11,
        fontweight="bold",
        y=0.99,
    )
    legend_patches = [mpatches.Patch(color=c, label=l) for _, l, c in markers]
    fig.legend(handles=legend_patches, loc="lower center", ncol=4, fontsize=8, bbox_to_anchor=(0.5, 0.0))

    out = os.path.join(result_dir, "fig1_timeseries.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"[run_{run_id}] Fig1 → {out}")

    cpu_mean, cpu_peak, cpu_auc = safe_stat(t_cpu, v_cpu)
    ram_mean, ram_peak, ram_auc = safe_stat(t_ram, v_ram)
    disk_mean, disk_peak, disk_auc = safe_stat(t_disk, v_disk)

    rx_peak = np.nan
    tx_peak = np.nan
    if v_rx is not None and len(v_rx) > 0 and not np.all(np.isnan(v_rx)):
        rx_peak = float(np.nanmax(v_rx) / 1000.0)
    if v_tx is not None and len(v_tx) > 0 and not np.all(np.isnan(v_tx)):
        tx_peak = float(np.nanmax(v_tx) / 1000.0)

    stats = dict(
        run=run_id,
        T_ready=(ready - start) if ready else np.nan,
        T_total=end - start,
        cpu_mean=cpu_mean,
        cpu_peak=cpu_peak,
        cpu_auc=cpu_auc,
        ram_mean=ram_mean,
        ram_peak=ram_peak,
        ram_auc=ram_auc,
        disk_mean=disk_mean,
        disk_peak=disk_peak,
        disk_auc=disk_auc,
        net_rx_peak_kbps=rx_peak,
        net_tx_peak_kbps=tx_peak,
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
        cols = ["run", "T_ready", "T_total", "cpu_peak", "ram_peak", "net_rx_peak_kbps"]
        cols = [c for c in cols if c in df.columns]
        print(df[cols].to_string(index=False))


if __name__ == "__main__":
    main()
