#!/usr/bin/env python3
import argparse
import shutil
from pathlib import Path
import math

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


def read_kv_log(path: Path) -> dict:
    d = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def read_netdata_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if df.empty:
        return df
    tcol = df.columns[0]
    df[tcol] = pd.to_numeric(df[tcol], errors="coerce")
    df = df.dropna(subset=[tcol]).copy()
    tmax = df[tcol].max()
    if isinstance(tmax, (int, float)) and tmax > 1e12:
        df[tcol] = df[tcol] / 1000.0
    return df


def pick_series(df: pd.DataFrame, kind: str) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    tcol = df.columns[0]
    cols = [c for c in df.columns if c != tcol]
    ncols = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
    if not ncols:
        return pd.Series(dtype=float)

    lk = kind.lower()

    if lk == "cpu":
        idle_cols = [c for c in ncols if "idle" in c.lower()]
        if idle_cols:
            return 100.0 - df[idle_cols[0]].astype(float)
        if len(ncols) == 1:
            return df[ncols[0]].astype(float)
        return df[ncols].astype(float).sum(axis=1)

    if lk == "ram":
        used_cols = [c for c in ncols if "used" in c.lower()]
        if used_cols:
            return df[used_cols[0]].astype(float)
        return df[ncols[0]].astype(float)

    if lk == "disk":
        util_cols = [c for c in ncols if "util" in c.lower()]
        if util_cols:
            return df[util_cols[0]].astype(float)
        return df[ncols[0]].astype(float)

    if lk == "net_rx":
        rx_cols = [c for c in ncols if ("received" in c.lower()) or (c.lower() in ("rx", "in"))]
        if rx_cols:
            return df[rx_cols[0]].astype(float)
        return df[ncols[0]].astype(float)

    if lk == "net_tx":
        tx_cols = [c for c in ncols if ("sent" in c.lower()) or (c.lower() in ("tx", "out"))]
        if tx_cols:
            return df[tx_cols[0]].astype(float)
        if len(ncols) >= 2:
            return df[ncols[1]].astype(float)
        return pd.Series(dtype=float)

    return df[ncols[0]].astype(float)


def auc_trapz(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 2 or len(y) < 2:
        return float("nan")
    return float(np.trapz(y, x))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", required=True)
    ap.add_argument("--run", required=True, type=int)
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    step = args.step
    run_id = args.run

    log_file = repo_root / "logs" / "redacted" / step / f"run_{run_id}.log"
    req_csv = repo_root / "logs" / "redacted" / step / f"run_{run_id}_requests.csv"

    data_dir = repo_root / "data" / "netdata" / step / f"run_{run_id}"
    result_dir = repo_root / "results" / step / f"run_{run_id}"
    result_dir.mkdir(parents=True, exist_ok=True)

    kv = read_kv_log(log_file)
    start_epoch = int(kv.get("START_EPOCH", "0"))
    ready_epoch = kv.get("READY_EPOCH", "NA")
    load_start_epoch = kv.get("LOAD_START_EPOCH", "NA")
    load_end_epoch = kv.get("LOAD_END_EPOCH", "NA")
    end_epoch = int(kv.get("END_EPOCH", str(start_epoch)))

    def parse_epoch(v):
        if v in (None, "", "NA"):
            return None
        try:
            return int(v)
        except Exception:
            return None

    ready_epoch_i = parse_epoch(ready_epoch)
    load_start_i = parse_epoch(load_start_epoch)
    load_end_i = parse_epoch(load_end_epoch)

    cpu_df = read_netdata_csv(data_dir / "system_cpu.csv")
    ram_df = read_netdata_csv(data_dir / "system_ram.csv")

    disk_files = list(data_dir.glob("disk_util_*.csv"))
    net_files = list(data_dir.glob("net_*.csv"))

    disk_df = read_netdata_csv(disk_files[0]) if disk_files else pd.DataFrame()
    net_df = read_netdata_csv(net_files[0]) if net_files else pd.DataFrame()

    # time axis (seconds from START)
    def rel_time(df):
        if df.empty:
            return np.array([])
        tcol = df.columns[0]
        return (df[tcol].astype(float).to_numpy() - float(start_epoch))

    cpu_t = rel_time(cpu_df)
    ram_t = rel_time(ram_df)
    disk_t = rel_time(disk_df)
    net_t = rel_time(net_df)

    cpu_y = pick_series(cpu_df, "cpu").to_numpy()
    ram_y = pick_series(ram_df, "ram").to_numpy()
    disk_y = pick_series(disk_df, "disk").to_numpy()
    net_rx = pick_series(net_df, "net_rx").to_numpy()
    net_tx = pick_series(net_df, "net_tx").to_numpy()

    fig, axes = plt.subplots(4, 1, figsize=(12, 10), sharex=True)

    axes[0].plot(cpu_t, cpu_y, label="CPU(active)")
    axes[0].set_ylabel("CPU")

    axes[1].plot(ram_t, ram_y, label="RAM(used)")
    axes[1].set_ylabel("RAM")

    if len(disk_t) and len(disk_y):
        axes[2].plot(disk_t, disk_y, label="Disk util")
    axes[2].set_ylabel("Disk")

    if len(net_t) and len(net_rx):
        axes[3].plot(net_t, net_rx, label="Net rx")
    if len(net_t) and len(net_tx):
        axes[3].plot(net_t, net_tx, label="Net tx")
    axes[3].set_ylabel("Net")
    axes[3].set_xlabel("Seconds from START")

    markers = [
        (0, "START"),
        ((ready_epoch_i - start_epoch) if ready_epoch_i else None, "READY"),
        ((load_start_i - start_epoch) if load_start_i else None, "LOAD_START"),
        ((load_end_i - start_epoch) if load_end_i else None, "LOAD_END"),
        ((end_epoch - start_epoch), "END"),
    ]
    for ax in axes:
        for x, name in markers:
            if x is None:
                continue
            ax.axvline(x=x, linestyle="--")
        ax.legend(loc="upper right")

    fig.tight_layout()
    out_fig = result_dir / "fig1_timeseries.png"
    fig.savefig(out_fig, dpi=150)
    plt.close(fig)

    # stats
    def basic_stats(t, y):
        if len(t) < 2 or len(y) < 2:
            return (float("nan"), float("nan"), float("nan"))
        mean = float(np.nanmean(y))
        peak = float(np.nanmax(y))
        auc = auc_trapz(t, y)
        return (mean, peak, auc)

    cpu_mean, cpu_peak, cpu_auc = basic_stats(cpu_t, cpu_y)
    ram_mean, ram_peak, ram_auc = basic_stats(ram_t, ram_y)
    disk_mean, disk_peak, disk_auc = basic_stats(disk_t, disk_y)
    rx_mean, rx_peak, rx_auc = basic_stats(net_t, net_rx) if len(net_rx) else (float("nan"), float("nan"), float("nan"))
    tx_mean, tx_peak, tx_auc = basic_stats(net_t, net_tx) if len(net_tx) else (float("nan"), float("nan"), float("nan"))

    req_latency_mean = float("nan")
    req_latency_p95 = float("nan")
    req_latency_max = float("nan")
    req_count = 0

    if req_csv.exists():
        rq = pd.read_csv(req_csv)
        if "latency_ms" in rq.columns and not rq.empty:
            lat = pd.to_numeric(rq["latency_ms"], errors="coerce").dropna()
            req_count = int(lat.shape[0])
            if req_count > 0:
                req_latency_mean = float(lat.mean())
                req_latency_p95 = float(np.percentile(lat.to_numpy(), 95))
                req_latency_max = float(lat.max())

    t_ready = float(ready_epoch_i - start_epoch) if ready_epoch_i else float("nan")
    t_total = float(end_epoch - start_epoch)

    stats = pd.DataFrame([{
        "run_id": run_id,
        "start_epoch": start_epoch,
        "ready_epoch": (ready_epoch_i if ready_epoch_i else np.nan),
        "load_start_epoch": (load_start_i if load_start_i else np.nan),
        "load_end_epoch": (load_end_i if load_end_i else np.nan),
        "end_epoch": end_epoch,
        "t_ready_sec": t_ready,
        "t_total_sec": t_total,
        "cpu_mean": cpu_mean, "cpu_peak": cpu_peak, "cpu_auc": cpu_auc,
        "ram_mean": ram_mean, "ram_peak": ram_peak, "ram_auc": ram_auc,
        "disk_mean": disk_mean, "disk_peak": disk_peak, "disk_auc": disk_auc,
        "net_rx_mean": rx_mean, "net_rx_peak": rx_peak, "net_rx_auc": rx_auc,
        "net_tx_mean": tx_mean, "net_tx_peak": tx_peak, "net_tx_auc": tx_auc,
        "req_count": req_count,
        "req_latency_mean_ms": req_latency_mean,
        "req_latency_p95_ms": req_latency_p95,
        "req_latency_max_ms": req_latency_max,
    }])

    stats.to_csv(result_dir / "stats.csv", index=False)

    # copy log
    shutil.copy2(log_file, result_dir / "redacted.log")


if __name__ == "__main__":
    main()
