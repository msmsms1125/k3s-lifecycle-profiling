#!/usr/bin/env python3
import os
import re
import glob
import argparse
from typing import Optional, Tuple, List, Dict

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# -----------------------------
# Log parsing (START/READY/END)
# -----------------------------
EPOCH_RE = re.compile(r'^(START_EPOCH|READY_EPOCH|END_EPOCH)=(\d+)\s*$')

def parse_epochs(log_path: str) -> Dict[str, Optional[int]]:
    out = {"START_EPOCH": None, "READY_EPOCH": None, "END_EPOCH": None}
    if not os.path.exists(log_path):
        return out
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = EPOCH_RE.match(line.strip())
            if not m:
                continue
            k, v = m.group(1), int(m.group(2))
            out[k] = v
    return out


# -----------------------------
# Netdata CSV parsing (robust)
# -----------------------------
def _find_time_col(df: pd.DataFrame) -> str:
    for c in ["time", "Time", "timestamp", "Timestamp", "datetime", "Date"]:
        if c in df.columns:
            return c
    return df.columns[0]

def _to_seconds_array(series: pd.Series) -> np.ndarray:
    s_num = pd.to_numeric(series, errors="coerce")
    if s_num.notna().mean() > 0.9:
        x = s_num.to_numpy(dtype=float)
        # ms -> sec heuristic
        if np.nanmedian(x) > 1e12:
            x = x / 1000.0
        return x

    dt = pd.to_datetime(series, errors="coerce", utc=True)
    if dt.notna().mean() > 0.9:
        return (dt.view("int64") / 1e9).to_numpy(dtype=float)

    raise ValueError("Cannot parse time column to epoch seconds.")

def load_netdata_csv(path: str) -> Tuple[np.ndarray, pd.DataFrame]:
    df = pd.read_csv(path)
    if df.empty:
        raise ValueError(f"Empty CSV: {path}")
    tcol = _find_time_col(df)
    t = _to_seconds_array(df[tcol])
    df2 = df.drop(columns=[tcol])
    for c in df2.columns:
        df2[c] = pd.to_numeric(df2[c], errors="coerce")
    df2 = df2.dropna(axis=1, how="all")
    return t, df2

def pick_col(df: pd.DataFrame, keywords: List[str]) -> Optional[str]:
    cols = list(df.columns)
    lower = {c: c.lower() for c in cols}
    for kw in keywords:
        for c in cols:
            if kw in lower[c]:
                return c
    return None

def first_numeric_col(df: pd.DataFrame) -> Optional[str]:
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]):
            return c
    return None


# -----------------------------
# Series extractors
# -----------------------------
def cpu_usage_percent(df: pd.DataFrame) -> pd.Series:
    idle = pick_col(df, ["idle"])
    if idle is not None:
        return 100.0 - df[idle]
    usage = pick_col(df, ["usage"])
    if usage is not None:
        return df[usage]
    # sum of states fallback
    states = [c for c in df.columns if any(k in c.lower() for k in ["user", "system", "iowait", "nice", "irq", "softirq", "steal"])]
    if states:
        return df[states].sum(axis=1)
    raise ValueError("Cannot derive CPU usage from columns.")

def ram_used_mib(df: pd.DataFrame) -> pd.Series:
    used = pick_col(df, ["used"])
    if used is None:
        used = first_numeric_col(df)
    if used is None:
        raise ValueError("No numeric RAM column.")
    s = df[used].astype(float)
    med = np.nanmedian(s.to_numpy())
    # bytes -> MiB
    if med > 1e9:
        return s / (1024.0 * 1024.0)
    # KiB -> MiB
    if med > 1e6:
        return s / 1024.0
    return s

def disk_util_percent(df: pd.DataFrame) -> pd.Series:
    util = pick_col(df, ["util", "busy"])
    if util is None:
        util = first_numeric_col(df)
    if util is None:
        raise ValueError("No numeric disk util column.")
    return df[util].astype(float)

def disk_io_kbps(df: pd.DataFrame) -> pd.Series:
    r = pick_col(df, ["read"])
    w = pick_col(df, ["write"])
    if r is not None and w is not None:
        s = df[r].astype(float) + df[w].astype(float)
    else:
        c = first_numeric_col(df)
        if c is None:
            raise ValueError("No numeric disk io column.")
        s = df[c].astype(float)
    med = np.nanmedian(s.to_numpy())
    # bytes/s -> KB/s
    if med > 1e6:
        return s / 1024.0
    return s


# -----------------------------
# Stats helpers
# -----------------------------
def auc_trapezoid(t_sec: np.ndarray, y: np.ndarray) -> float:
    order = np.argsort(t_sec)
    t = t_sec[order]
    v = y[order]
    mask = np.isfinite(t) & np.isfinite(v)
    t = t[mask]
    v = v[mask]
    if len(t) < 2:
        return float("nan")
    return float(np.trapezoid(v, t))


def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


# -----------------------------
# Plot helpers
# -----------------------------
def plot_fig1_cpu_ram_disk(out_path: str, t_rel: np.ndarray, cpu: np.ndarray, ram: np.ndarray, du: np.ndarray,
                           t_ready: Optional[float], t_end: Optional[float]) -> None:
    plt.figure(figsize=(12, 6))
    plt.plot(t_rel, cpu, label="CPU usage (%)")
    plt.plot(t_rel, ram, label="RAM used (MiB)")
    plt.plot(t_rel, du, label="Disk util (%)")

    plt.axvline(0.0, linestyle="--", linewidth=1, label="START")
    if t_ready is not None:
        plt.axvline(t_ready, linestyle="--", linewidth=1, label="READY")
    if t_end is not None:
        plt.axvline(t_end, linestyle="--", linewidth=1, label="END")

    plt.xlabel("Time since START (sec)  [pre window can be negative]")
    plt.ylabel("Value")
    plt.title("Step02 start_master: timeseries (CPU/RAM/Disk util)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def plot_fig1_disk_io(out_path: str, t_rel: np.ndarray, dio: np.ndarray,
                      t_ready: Optional[float], t_end: Optional[float]) -> None:
    plt.figure(figsize=(12, 4))
    plt.plot(t_rel, dio, label="Disk IO (KB/s)")
    plt.axvline(0.0, linestyle="--", linewidth=1, label="START")
    if t_ready is not None:
        plt.axvline(t_ready, linestyle="--", linewidth=1, label="READY")
    if t_end is not None:
        plt.axvline(t_end, linestyle="--", linewidth=1, label="END")
    plt.xlabel("Time since START (sec)  [pre window can be negative]")
    plt.ylabel("KB/s")
    plt.title("Step02 start_master: timeseries (Disk IO)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def plot_box(out_path: str, values: List[float], title: str, ylabel: str) -> None:
    plt.figure(figsize=(7, 4))
    plt.boxplot(values, showmeans=True, tick_labels=["runs"])
    plt.title(title)
    plt.ylabel(ylabel)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


# -----------------------------
# Main
# -----------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data_root", default="data/netdata/step02_start_master")
    ap.add_argument("--logs_root", default="logs/redacted/step02_start_master")
    ap.add_argument("--out_root",  default="results/step02_start_master")
    ap.add_argument("--event_only", action="store_true",
                    help="If set, stats are computed only on [START..END]. Otherwise uses [EXPORT..END] when export has pre window.")
    args = ap.parse_args()

    run_dirs = sorted(glob.glob(os.path.join(args.data_root, "run_*")))
    if not run_dirs:
        raise SystemExit(f"No runs found: {args.data_root}/run_*")

    ensure_dir(args.out_root)

    rows = []
    for rd in run_dirs:
        run = os.path.basename(rd)
        log_path = os.path.join(args.logs_root, f"{run}.log")
        epochs = parse_epochs(log_path)
        start = epochs["START_EPOCH"]
        ready = epochs["READY_EPOCH"]
        end = epochs["END_EPOCH"]

        if start is None or end is None:
            raise SystemExit(f"Missing START/END in log: {log_path}")

        # find disk files (device name may vary)
        cpu_path = os.path.join(rd, "system_cpu.csv")
        ram_path = os.path.join(rd, "system_ram.csv")
        du_list  = glob.glob(os.path.join(rd, "disk_util_*.csv"))
        dio_list = glob.glob(os.path.join(rd, "disk_io_*.csv"))

        if not os.path.exists(cpu_path): raise SystemExit(f"Missing: {cpu_path}")
        if not os.path.exists(ram_path): raise SystemExit(f"Missing: {ram_path}")
        if not du_list:  raise SystemExit(f"Missing: {rd}/disk_util_*.csv")
        if not dio_list: raise SystemExit(f"Missing: {rd}/disk_io_*.csv")

        du_path  = sorted(du_list)[0]
        dio_path = sorted(dio_list)[0]
        disk_dev = os.path.basename(du_path).replace("disk_util_", "").replace(".csv", "")

        t_cpu, df_cpu = load_netdata_csv(cpu_path)
        t_ram, df_ram = load_netdata_csv(ram_path)
        t_du,  df_du  = load_netdata_csv(du_path)
        t_dio, df_dio = load_netdata_csv(dio_path)

        cpu = cpu_usage_percent(df_cpu).to_numpy()
        ram = ram_used_mib(df_ram).to_numpy()
        du  = disk_util_percent(df_du).to_numpy()
        dio = disk_io_kbps(df_dio).to_numpy()

        # plotting x-axis: seconds since START (pre window negative)
        t_rel_cpu = t_cpu - float(start)
        t_rel_ram = t_ram - float(start)
        t_rel_du  = t_du  - float(start)
        t_rel_dio = t_dio - float(start)

        t_ready = float(ready - start) if ready is not None else None
        t_end   = float(end - start)

        # per-run output folder
        run_out = os.path.join(args.out_root, run)
        ensure_dir(run_out)

        # For a clean fig, we plot using cpu time as x, but series are different timebases.
        # To avoid resampling complexity, we plot each with its own x in same axes by re-plotting.
        # (matplotlib accepts different x arrays)
        plt.figure(figsize=(12, 6))
        plt.plot(t_rel_cpu, cpu, label="CPU usage (%)")
        plt.plot(t_rel_ram, ram, label="RAM used (MiB)")
        plt.plot(t_rel_du,  du,  label=f"Disk util (%) [{disk_dev}]")
        plt.axvline(0.0, linestyle="--", linewidth=1, label="START")
        if t_ready is not None:
            plt.axvline(t_ready, linestyle="--", linewidth=1, label="READY")
        plt.axvline(t_end, linestyle="--", linewidth=1, label="END")
        plt.xlabel("Time since START (sec)  [pre window can be negative]")
        plt.ylabel("Value")
        plt.title(f"Step02 start_master: timeseries (CPU/RAM/Disk util) - {run}")
        plt.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(run_out, "fig1_timeseries_cpu_ram_disk.png"), dpi=150)
        plt.close()

        plt.figure(figsize=(12, 4))
        plt.plot(t_rel_dio, dio, label=f"Disk IO (KB/s) [{disk_dev}]")
        plt.axvline(0.0, linestyle="--", linewidth=1, label="START")
        if t_ready is not None:
            plt.axvline(t_ready, linestyle="--", linewidth=1, label="READY")
        plt.axvline(t_end, linestyle="--", linewidth=1, label="END")
        plt.xlabel("Time since START (sec)  [pre window can be negative]")
        plt.ylabel("KB/s")
        plt.title(f"Step02 start_master: timeseries (Disk IO) - {run}")
        plt.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(run_out, "fig1_timeseries_disk_io.png"), dpi=150)
        plt.close()

        # copy redacted log into results/run_*/redacted.log (Step01과 동일)
        if os.path.exists(log_path):
            with open(log_path, "rb") as src, open(os.path.join(run_out, "redacted.log"), "wb") as dst:
                dst.write(src.read())

        # stats window
        # 기본: export가 pre 포함이므로 "pre 포함 전체"가 되는데,
        # 이벤트만 보고 싶으면 --event_only로 START..END만 계산
        def clip(t, y, t0, t1):
            m = (t >= t0) & (t <= t1)
            return t[m], y[m]

        t0 = float(start)
        t1 = float(end)

        if args.event_only:
            # compute stats only on [START..END]
            tc, yc = clip(t_cpu, cpu, t0, t1)
            tr, yr = clip(t_ram, ram, t0, t1)
            tu, yu = clip(t_du,  du,  t0, t1)
            ti, yi = clip(t_dio, dio, t0, t1)
        else:
            # include whatever is exported (usually [START-PRE .. END])
            tc, yc = t_cpu, cpu
            tr, yr = t_ram, ram
            tu, yu = t_du,  du
            ti, yi = t_dio, dio

        cpu_mean = float(np.nanmean(yc)); cpu_peak = float(np.nanmax(yc)); cpu_auc = auc_trapezoid(tc, yc)
        ram_mean = float(np.nanmean(yr)); ram_peak = float(np.nanmax(yr)); ram_auc = auc_trapezoid(tr, yr)
        du_mean  = float(np.nanmean(yu)); du_peak  = float(np.nanmax(yu)); du_auc  = auc_trapezoid(tu, yu)
        dio_mean = float(np.nanmean(yi)); dio_peak = float(np.nanmax(yi)); dio_auc = auc_trapezoid(ti, yi)

        t_ready_sec = float(ready - start) if ready is not None else float("nan")
        t_total_sec = float(end - start)

        rows.append({
            "run": run,
            "disk_dev": disk_dev,
            "start_epoch": start,
            "ready_epoch": ready,
            "end_epoch": end,
            "t_ready_sec": t_ready_sec,
            "t_total_sec": t_total_sec,
            "cpu_mean": cpu_mean,
            "cpu_peak": cpu_peak,
            "cpu_auc": cpu_auc,
            "ram_mean_mib": ram_mean,
            "ram_peak_mib": ram_peak,
            "ram_auc_mibsec": ram_auc,
            "disk_util_mean": du_mean,
            "disk_util_peak": du_peak,
            "disk_util_auc": du_auc,
            "disk_io_mean_kbps": dio_mean,
            "disk_io_peak_kbps": dio_peak,
            "disk_io_auc_kb": dio_auc,
        })

    df = pd.DataFrame(rows).sort_values("run")
    out_csv = os.path.join(args.out_root, "summary_step02.csv")
    df.to_csv(out_csv, index=False)
    print(f"Saved: {out_csv}")

    # Fig2: boxplots across runs (Step01처럼 “요약 분포”)
    plot_box(os.path.join(args.out_root, "fig2_t_ready_box.png"),
             df["t_ready_sec"].dropna().tolist(),
             "T_ready distribution (start_master)", "seconds")

    plot_box(os.path.join(args.out_root, "fig2_t_total_box.png"),
             df["t_total_sec"].dropna().tolist(),
             "T_total distribution (start_master)", "seconds")

    plot_box(os.path.join(args.out_root, "fig2_cpu_mean_box.png"),
             df["cpu_mean"].dropna().tolist(),
             "CPU mean distribution (start_master)", "CPU usage (%)")

    plot_box(os.path.join(args.out_root, "fig2_ram_mean_box.png"),
             df["ram_mean_mib"].dropna().tolist(),
             "RAM mean distribution (start_master)", "RAM used (MiB)")

    plot_box(os.path.join(args.out_root, "fig2_disk_util_mean_box.png"),
             df["disk_util_mean"].dropna().tolist(),
             "Disk util mean distribution (start_master)", "Disk util (%)")

    print("Saved Fig2 under:", args.out_root)


if __name__ == "__main__":
    main()

