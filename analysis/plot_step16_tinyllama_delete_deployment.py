#!/usr/bin/env python3
import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def parse_epochs(log_path: Path) -> dict:
    txt = log_path.read_text(errors="ignore")
    keys = ["START_EPOCH", "DELETE_COMPLETE_EPOCH", "END_EPOCH"]
    out = {}
    for k in keys:
        m = re.search(rf"{k}\s*=\s*(\d+)", txt)
        if not m:
            m = re.search(rf"{k}\s+(\d+)", txt)
        if not m:
            raise RuntimeError(f"{k} not found in {log_path}")
        out[k] = int(m.group(1))
    return out


def read_netdata_csv(p: Path) -> pd.DataFrame:
    df = pd.read_csv(p, comment="#")
    if df.shape[1] < 2:
        raise RuntimeError(f"unexpected csv format: {p}")
    df.columns = [str(c).strip() for c in df.columns]
    time_col = "time" if "time" in df.columns else df.columns[0]
    df[time_col] = pd.to_numeric(df[time_col], errors="coerce")
    df = df.dropna(subset=[time_col]).copy()
    df = df.sort_values(time_col)
    df = df.rename(columns={time_col: "time"})
    for c in df.columns:
        if c == "time":
            continue
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def cpu_series(df: pd.DataFrame) -> pd.Series:
    cols = [c for c in df.columns if c != "time"]
    lower = {c.lower(): c for c in cols}
    if "idle" in lower:
        return 100.0 - df[lower["idle"]]
    return df[cols].sum(axis=1, skipna=True)


def ram_series(df: pd.DataFrame) -> pd.Series:
    cols = [c for c in df.columns if c != "time"]
    lower = {c.lower(): c for c in cols}
    if "used" in lower:
        return df[lower["used"]]
    return df[cols].max(axis=1, skipna=True)


def first_matching(df: pd.DataFrame, patterns: list[str]) -> str | None:
    cols = [c for c in df.columns if c != "time"]
    for pat in patterns:
        for c in cols:
            if pat in c.lower():
                return c
    return None


def disk_series(df: pd.DataFrame) -> pd.Series:
    c = first_matching(df, ["util", "utilization"])
    if c is None:
        cols = [c for c in df.columns if c != "time"]
        c = cols[0]
    return df[c]


def net_rx_tx(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    rx_c = first_matching(df, ["received", "rx"])
    tx_c = first_matching(df, ["sent", "tx"])
    cols = [c for c in df.columns if c != "time"]
    if rx_c is None or tx_c is None:
        if len(cols) >= 2:
            rx_c = cols[0]
            tx_c = cols[1]
        elif len(cols) == 1:
            rx_c = cols[0]
            tx_c = cols[0]
        else:
            raise RuntimeError("no net columns")
    return df[rx_c], df[tx_c]


def auc(t: np.ndarray, y: np.ndarray) -> float:
    if len(t) < 2:
        return float("nan")
    return float(np.trapz(y, t))


def plateau_time_seconds(t_rel: np.ndarray, y: np.ndarray, tail_points: int = 12, tol_ratio: float = 0.05) -> float:
    if len(y) < max(3, tail_points):
        return float("nan")
    tail = y[-tail_points:]
    p = float(np.nanmedian(tail))
    y0 = float(y[0])
    if not np.isfinite(p) or not np.isfinite(y0):
        return float("nan")
    span = abs(y0 - p)
    tol = tol_ratio * span
    thr = p + tol
    for i in range(len(y)):
        if y[i] <= thr:
            return float(t_rel[i])
    return float("nan")


def stable_time_seconds(t_rel: np.ndarray, ys: list[np.ndarray], tail_points: int = 12, tol_ratio: float = 0.05, consec: int = 3) -> float:
    if len(t_rel) < max(consec + 1, tail_points):
        return float("nan")
    plates = []
    for y in ys:
        tail = y[-tail_points:]
        plates.append(float(np.nanmedian(tail)))
    y0s = [float(y[0]) for y in ys]
    spans = [abs(y0s[i] - plates[i]) for i in range(len(ys))]
    tols = [tol_ratio * s for s in spans]
    for i in range(len(t_rel) - consec + 1):
        ok = True
        for j, y in enumerate(ys):
            thr = plates[j] + tols[j]
            window = y[i:i+consec]
            if not np.all(np.isfinite(window)):
                ok = False
                break
            if np.any(window > thr):
                ok = False
                break
        if ok:
            return float(t_rel[i])
    return float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", required=True)
    ap.add_argument("--run", required=True)
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    step = args.step
    run = str(args.run)

    log_path = repo_root / "logs" / "redacted" / step / f"run_{run}.log"
    data_dir = repo_root / "data" / "netdata" / step / f"run_{run}"
    result_dir = repo_root / "results" / step / f"run_{run}"
    result_dir.mkdir(parents=True, exist_ok=True)

    epochs = parse_epochs(log_path)
    start = epochs["START_EPOCH"]
    delete_done = epochs["DELETE_COMPLETE_EPOCH"]
    end = epochs["END_EPOCH"]

    cpu_df = read_netdata_csv(data_dir / "system_cpu.csv")
    ram_df = read_netdata_csv(data_dir / "system_ram.csv")

    disk_files = sorted(data_dir.glob("disk_util_*.csv"))
    if not disk_files:
        raise RuntimeError("disk_util csv not found")
    disk_df = read_netdata_csv(disk_files[0])

    net_files = sorted(data_dir.glob("net_*.csv"))
    if not net_files:
        raise RuntimeError("net csv not found")
    net_df = read_netdata_csv(net_files[0])

    cpu_y = cpu_series(cpu_df).to_numpy(dtype=float)
    ram_y = ram_series(ram_df).to_numpy(dtype=float)
    disk_y = disk_series(disk_df).to_numpy(dtype=float)
    rx_y, tx_y = net_rx_tx(net_df)
    rx_y = rx_y.to_numpy(dtype=float)
    tx_y = tx_y.to_numpy(dtype=float)

    t_cpu = cpu_df["time"].to_numpy(dtype=float)
    t_ram = ram_df["time"].to_numpy(dtype=float)
    t_disk = disk_df["time"].to_numpy(dtype=float)
    t_net = net_df["time"].to_numpy(dtype=float)

    t_rel_cpu = t_cpu - start
    t_rel_ram = t_ram - start
    t_rel_disk = t_disk - start
    t_rel_net = t_net - start

    fig, axes = plt.subplots(4, 1, figsize=(10, 10), sharex=True)

    axes[0].plot(t_rel_cpu, cpu_y)
    axes[0].axvline(0, linestyle="--")
    axes[0].axvline(delete_done - start, linestyle="--")
    axes[0].set_ylabel("CPU")

    axes[1].plot(t_rel_ram, ram_y)
    axes[1].axvline(0, linestyle="--")
    axes[1].axvline(delete_done - start, linestyle="--")
    axes[1].set_ylabel("RAM")

    axes[2].plot(t_rel_disk, disk_y)
    axes[2].axvline(0, linestyle="--")
    axes[2].axvline(delete_done - start, linestyle="--")
    axes[2].set_ylabel("Disk util")

    axes[3].plot(t_rel_net, rx_y, label="rx")
    axes[3].plot(t_rel_net, tx_y, label="tx")
    axes[3].axvline(0, linestyle="--")
    axes[3].axvline(delete_done - start, linestyle="--")
    axes[3].set_ylabel("Net")
    axes[3].set_xlabel("seconds since START")
    axes[3].legend()

    fig.tight_layout()
    fig.savefig(result_dir / "fig1_timeseries.png", dpi=150)
    plt.close(fig)

    t_delete = delete_done - start
    t_total = end - start

    cpu_mean = float(np.nanmean(cpu_y))
    cpu_peak = float(np.nanmax(cpu_y))
    cpu_auc = auc(t_cpu, cpu_y)

    ram_mean = float(np.nanmean(ram_y))
    ram_peak = float(np.nanmax(ram_y))
    ram_auc = auc(t_ram, ram_y)

    disk_mean = float(np.nanmean(disk_y))
    disk_peak = float(np.nanmax(disk_y))
    disk_auc = auc(t_disk, disk_y)

    rx_peak = float(np.nanmax(rx_y))
    tx_peak = float(np.nanmax(tx_y))
    rx_auc = auc(t_net, rx_y)
    tx_auc = auc(t_net, tx_y)

    mem_release_latency = plateau_time_seconds(t_rel_ram, ram_y, tail_points=12, tol_ratio=0.05)
    idle_recovery_time = stable_time_seconds(
        t_rel_cpu,
        ys=[cpu_y, ram_y],
        tail_points=12,
        tol_ratio=0.05,
        consec=3,
    )

    stats = pd.DataFrame([{
        "run": int(run),
        "START_EPOCH": start,
        "DELETE_COMPLETE_EPOCH": delete_done,
        "END_EPOCH": end,
        "T_delete": t_delete,
        "T_total": t_total,
        "cpu_mean": cpu_mean,
        "cpu_peak": cpu_peak,
        "cpu_auc": cpu_auc,
        "ram_mean": ram_mean,
        "ram_peak": ram_peak,
        "ram_auc": ram_auc,
        "disk_mean": disk_mean,
        "disk_peak": disk_peak,
        "disk_auc": disk_auc,
        "net_rx_peak": rx_peak,
        "net_tx_peak": tx_peak,
        "net_rx_auc": rx_auc,
        "net_tx_auc": tx_auc,
        "mem_release_latency_s": mem_release_latency,
        "idle_recovery_time_s": idle_recovery_time,
    }])
    stats.to_csv(result_dir / "stats.csv", index=False)


if __name__ == "__main__":
    main()
