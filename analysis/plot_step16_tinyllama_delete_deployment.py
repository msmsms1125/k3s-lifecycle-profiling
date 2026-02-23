#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional, Tuple, List

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


DEFAULT_TZ = "Asia/Seoul"


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


def _to_epoch_seconds_from_any_time(
    s: pd.Series,
    assume_tz: str,
    start_epoch: Optional[int] = None,
) -> pd.Series:
    # 1) Try numeric first
    t_num = pd.to_numeric(s, errors="coerce")
    if int(t_num.notna().sum()) > 0:
        t = t_num.astype(float)

        med = float(t.dropna().median())
        if med > 1e14:      # likely microseconds since epoch
            t = t / 1e6
        elif med > 1e11:    # likely milliseconds since epoch
            t = t / 1e3

        if start_epoch is not None:
            mx = float(t.dropna().max()) if int(t.dropna().shape[0]) > 0 else float("nan")
            if np.isfinite(mx) and mx < 1e7:
                t = t + float(start_epoch)

        return t

    dt = pd.to_datetime(s, errors="coerce")
    if int(dt.notna().sum()) == 0:
        raise RuntimeError("cannot parse time column: neither numeric nor datetime")

    if dt.dt.tz is None:
        dt = dt.dt.tz_localize(assume_tz)

    dt_utc = dt.dt.tz_convert("UTC")
    dt_utc_naive = dt_utc.dt.tz_localize(None)

    t = dt_utc_naive.astype("int64") / 1e9
    return t.astype(float)


def read_netdata_csv(p: Path, assume_tz: str, start_epoch: Optional[int]) -> pd.DataFrame:
    df = pd.read_csv(p, comment="#")
    if df.shape[1] < 2:
        raise RuntimeError(f"unexpected csv format: {p}")

    df.columns = [str(c).strip() for c in df.columns]
    time_col = "time" if "time" in df.columns else df.columns[0]

    df[time_col] = _to_epoch_seconds_from_any_time(df[time_col], assume_tz=assume_tz, start_epoch=start_epoch)
    df = df.dropna(subset=[time_col]).copy()
    df = df.sort_values(time_col).copy()
    df = df.rename(columns={time_col: "time"})

    for c in df.columns:
        if c == "time":
            continue
        df[c] = pd.to_numeric(df[c], errors="coerce")

    return df


def clip_df(df: pd.DataFrame, start: int, end: int, label: str) -> pd.DataFrame:
    out = df[(df["time"] >= float(start)) & (df["time"] <= float(end))].copy()
    if out.empty:
        tmin = float(df["time"].min()) if not df.empty else float("nan")
        tmax = float(df["time"].max()) if not df.empty else float("nan")
        raise RuntimeError(
            f"{label}: no points in [START_EPOCH, END_EPOCH]. "
            f"start={start}, end={end}, csv_time_min={tmin}, csv_time_max={tmax}"
        )
    return out


def first_matching(df: pd.DataFrame, patterns: List[str]) -> Optional[str]:
    cols = [c for c in df.columns if c != "time"]
    for pat in patterns:
        for c in cols:
            if pat in c.lower():
                return c
    return None


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


def disk_series(df: pd.DataFrame) -> pd.Series:
    c = first_matching(df, ["util", "utilization"])
    if c is None:
        cols = [c for c in df.columns if c != "time"]
        if not cols:
            raise RuntimeError("no disk columns")
        c = cols[0]
    return df[c]


def net_rx_tx(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
    rx_c = first_matching(df, ["received", "rx"])
    tx_c = first_matching(df, ["sent", "tx"])
    cols = [c for c in df.columns if c != "time"]

    if rx_c is None or tx_c is None:
        if len(cols) >= 2:
            rx_c, tx_c = cols[0], cols[1]
        elif len(cols) == 1:
            rx_c, tx_c = cols[0], cols[0]
        else:
            raise RuntimeError("no net columns")

    return df[rx_c], df[tx_c]


def auc(t: np.ndarray, y: np.ndarray) -> float:
    if len(t) < 2:
        return float("nan")
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(y, t))
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
        if np.isfinite(y[i]) and y[i] <= thr:
            return float(t_rel[i])
    return float("nan")


def _interp_to_base(t_base: np.ndarray, t_other: np.ndarray, y_other: np.ndarray) -> np.ndarray:
    m = np.isfinite(t_other) & np.isfinite(y_other)
    if int(m.sum()) < 2:
        return np.full_like(t_base, np.nan, dtype=float)
    to = t_other[m].astype(float)
    yo = y_other[m].astype(float)
    idx = np.argsort(to)
    to = to[idx]
    yo = yo[idx]
    return np.interp(t_base.astype(float), to, yo)


def stable_time_seconds(t_rel: np.ndarray, ys: List[np.ndarray], tail_points: int = 12, tol_ratio: float = 0.05, consec: int = 3) -> float:
    if len(t_rel) < max(consec + 1, tail_points):
        return float("nan")

    plates = []
    spans = []
    for y in ys:
        if len(y) < max(consec + 1, tail_points):
            return float("nan")
        p = float(np.nanmedian(y[-tail_points:]))
        y0 = float(y[0])
        if not np.isfinite(p) or not np.isfinite(y0):
            return float("nan")
        plates.append(p)
        spans.append(abs(y0 - p))

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
    ap.add_argument("--timezone", default=DEFAULT_TZ)
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    step = args.step
    run = str(args.run)
    tz = args.timezone

    log_path = repo_root / "logs" / "redacted" / step / f"run_{run}.log"
    data_dir = repo_root / "data" / "netdata" / step / f"run_{run}"
    result_dir = repo_root / "results" / step / f"run_{run}"
    result_dir.mkdir(parents=True, exist_ok=True)

    epochs = parse_epochs(log_path)
    start = epochs["START_EPOCH"]
    delete_done = epochs["DELETE_COMPLETE_EPOCH"]
    end = epochs["END_EPOCH"]

    cpu_df = clip_df(read_netdata_csv(data_dir / "system_cpu.csv", tz, start), start, end, "system_cpu.csv")
    ram_df = clip_df(read_netdata_csv(data_dir / "system_ram.csv", tz, start), start, end, "system_ram.csv")

    disk_files = sorted(data_dir.glob("disk_util_*.csv"))
    if not disk_files:
        raise RuntimeError("disk_util csv not found")
    disk_df = clip_df(read_netdata_csv(disk_files[0], tz, start), start, end, disk_files[0].name)

    net_files = sorted(data_dir.glob("net_*.csv"))
    if not net_files:
        raise RuntimeError("net csv not found")
    net_df = clip_df(read_netdata_csv(net_files[0], tz, start), start, end, net_files[0].name)

    cpu_y = cpu_series(cpu_df).to_numpy(dtype=float)
    ram_y = ram_series(ram_df).to_numpy(dtype=float)
    disk_y = disk_series(disk_df).to_numpy(dtype=float)
    rx_y_s, tx_y_s = net_rx_tx(net_df)
    rx_y = rx_y_s.to_numpy(dtype=float)
    tx_y = tx_y_s.to_numpy(dtype=float)

    t_cpu = cpu_df["time"].to_numpy(dtype=float)
    t_ram = ram_df["time"].to_numpy(dtype=float)
    t_disk = disk_df["time"].to_numpy(dtype=float)
    t_net = net_df["time"].to_numpy(dtype=float)

    t_rel_cpu = t_cpu - float(start)
    t_rel_ram = t_ram - float(start)
    t_rel_disk = t_disk - float(start)
    t_rel_net = t_net - float(start)

    t_delete = float(delete_done - start)
    t_total = float(end - start)

    fig, axes = plt.subplots(4, 1, figsize=(10, 10), sharex=True)

    axes[0].plot(t_rel_cpu, cpu_y)
    axes[0].axvline(0, linestyle="--")
    axes[0].axvline(t_delete, linestyle="--")
    axes[0].set_ylabel("CPU")

    axes[1].plot(t_rel_ram, ram_y)
    axes[1].axvline(0, linestyle="--")
    axes[1].axvline(t_delete, linestyle="--")
    axes[1].set_ylabel("RAM")

    axes[2].plot(t_rel_disk, disk_y)
    axes[2].axvline(0, linestyle="--")
    axes[2].axvline(t_delete, linestyle="--")
    axes[2].set_ylabel("Disk util")

    axes[3].plot(t_rel_net, rx_y, label="rx")
    axes[3].plot(t_rel_net, tx_y, label="tx")
    axes[3].axvline(0, linestyle="--")
    axes[3].axvline(t_delete, linestyle="--")
    axes[3].set_ylabel("Net")
    axes[3].set_xlabel("seconds since START")
    axes[3].legend()

    axes[3].set_xlim(0, t_total)
    fig.tight_layout()
    fig.savefig(result_dir / "fig1_timeseries.png", dpi=150)
    plt.close(fig)

    cpu_mean = float(np.nanmean(cpu_y))
    cpu_peak = float(np.nanmax(cpu_y))
    cpu_auc = auc(t_rel_cpu, cpu_y)

    ram_mean = float(np.nanmean(ram_y))
    ram_peak = float(np.nanmax(ram_y))
    ram_auc = auc(t_rel_ram, ram_y)

    disk_mean = float(np.nanmean(disk_y))
    disk_peak = float(np.nanmax(disk_y))
    disk_auc = auc(t_rel_disk, disk_y)

    rx_peak = float(np.nanmax(rx_y))
    tx_peak = float(np.nanmax(tx_y))
    rx_auc = auc(t_rel_net, rx_y)
    tx_auc = auc(t_rel_net, tx_y)

    mem_release_latency = plateau_time_seconds(t_rel_ram, ram_y, tail_points=12, tol_ratio=0.05)

    ram_on_cpu = _interp_to_base(t_rel_cpu, t_rel_ram, ram_y)
    idle_recovery_time = stable_time_seconds(
        t_rel_cpu,
        ys=[cpu_y, ram_on_cpu],
        tail_points=12,
        tol_ratio=0.05,
        consec=3,
    )

    stats = pd.DataFrame([{
        "run": int(run),
        "START_EPOCH": int(start),
        "DELETE_COMPLETE_EPOCH": int(delete_done),
        "END_EPOCH": int(end),
        "T_delete": float(t_delete),
        "T_total": float(t_total),
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
        "mem_release_latency_s": float(mem_release_latency),
        "idle_recovery_time_s": float(idle_recovery_time),
    }])
    stats.to_csv(result_dir / "stats.csv", index=False)


if __name__ == "__main__":
    main()
