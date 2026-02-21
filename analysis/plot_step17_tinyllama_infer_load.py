#!/usr/bin/env python3
import argparse, os, shutil
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def repo_root_from_here() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def read_kv_log(path: str) -> dict:
    d = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or "=" not in line:
                continue
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip()
    return d

def read_netdata_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path, comment="#")

def time_col(df: pd.DataFrame) -> str:
    for c in df.columns:
        if c.lower() in ("time", "timestamp"):
            return c
    return df.columns[0]

def pick_col(df: pd.DataFrame, keywords):
    tcol = time_col(df)
    value_cols = [c for c in df.columns if c != tcol]
    for kw in keywords:
        for c in value_cols:
            if kw in c.lower():
                return c
    return value_cols[0] if value_cols else None

def auc(t: np.ndarray, y: np.ndarray) -> float:
    if len(t) < 2:
        return float("nan")
    return float(np.trapz(y, t))

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", required=True)
    ap.add_argument("--run", type=int, required=True)
    args = ap.parse_args()

    root = repo_root_from_here()
    step = args.step
    run = args.run

    log_file = os.path.join(root, "logs", "redacted", step, f"run_{run}.log")
    req_csv = os.path.join(root, "logs", "redacted", step, f"run_{run}_requests.csv")
    net_dir = os.path.join(root, "data", "netdata", step, f"run_{run}")
    out_dir = os.path.join(root, "results", step, f"run_{run}")
    os.makedirs(out_dir, exist_ok=True)

    meta = read_kv_log(log_file)

    start_epoch = int(meta["START_EPOCH"])
    ready_epoch = int(meta["READY_EPOCH"])
    load_start = int(meta["LOAD_START_EPOCH"])
    load_end = int(meta["LOAD_END_EPOCH"])
    end_epoch = int(meta["END_EPOCH"])

    req = pd.read_csv(req_csv)
    req["ttft_sec"] = pd.to_numeric(req["ttft_sec"], errors="coerce")
    req["total_sec"] = pd.to_numeric(req["total_sec"], errors="coerce")
    req["queue_delay_sec"] = pd.to_numeric(req["queue_delay_sec"], errors="coerce")

    ttft_mean = float(req["ttft_sec"].mean(skipna=True))
    total_mean = float(req["total_sec"].mean(skipna=True))
    queue_mean = float(req["queue_delay_sec"].mean(skipna=True))

    cpu = read_netdata_csv(os.path.join(net_dir, "system_cpu.csv"))
    ram = read_netdata_csv(os.path.join(net_dir, "system_ram.csv"))
    disk = read_netdata_csv(os.path.join(net_dir, "disk_util_mmcblk0.csv"))
    net = read_netdata_csv(os.path.join(net_dir, "net_eth0.csv"))

    t_cpu_col = time_col(cpu)
    t_cpu = cpu[t_cpu_col].to_numpy(dtype=float)
    cpu_cols = [c for c in cpu.columns if c != t_cpu_col]
    idle_cols = [c for c in cpu_cols if "idle" in c.lower()]
    if idle_cols:
        cpu_used = 100.0 - cpu[idle_cols[0]].to_numpy(dtype=float)
    else:
        cpu_used = cpu[cpu_cols].sum(axis=1).to_numpy(dtype=float)

    t_ram_col = time_col(ram)
    t_ram = ram[t_ram_col].to_numpy(dtype=float)
    ram_used_col = pick_col(ram, ["used"])
    ram_used = ram[ram_used_col].to_numpy(dtype=float)

    t_disk_col = time_col(disk)
    t_disk = disk[t_disk_col].to_numpy(dtype=float)
    disk_col = pick_col(disk, ["util", "utilization"])
    disk_util = disk[disk_col].to_numpy(dtype=float)

    t_net_col = time_col(net)
    t_net = net[t_net_col].to_numpy(dtype=float)
    rx_col = pick_col(net, ["received", "recv", "rx"])
    tx_col = pick_col(net, ["sent", "send", "tx"])
    net_rx = net[rx_col].to_numpy(dtype=float)
    net_tx = net[tx_col].to_numpy(dtype=float)

    stats = pd.DataFrame([{
        "run": run,
        "START_EPOCH": start_epoch,
        "READY_EPOCH": ready_epoch,
        "LOAD_START_EPOCH": load_start,
        "LOAD_END_EPOCH": load_end,
        "END_EPOCH": end_epoch,
        "ttft_mean": ttft_mean,
        "total_mean": total_mean,
        "queue_mean": queue_mean,
        "cpu_mean": float(np.nanmean(cpu_used)),
        "cpu_peak": float(np.nanmax(cpu_used)),
        "cpu_auc": auc(t_cpu, cpu_used),
        "ram_mean": float(np.nanmean(ram_used)),
        "ram_peak": float(np.nanmax(ram_used)),
        "ram_auc": auc(t_ram, ram_used),
        "disk_mean": float(np.nanmean(disk_util)),
        "disk_peak": float(np.nanmax(disk_util)),
        "disk_auc": auc(t_disk, disk_util),
        "net_rx_peak": float(np.nanmax(net_rx)),
        "net_tx_peak": float(np.nanmax(net_tx)),
        "net_rx_auc": auc(t_net, net_rx),
        "net_tx_auc": auc(t_net, net_tx),
    }])
    stats.to_csv(os.path.join(out_dir, "stats.csv"), index=False)

    def rel(t): return t - start_epoch

    fig, axes = plt.subplots(4, 1, figsize=(12, 10), sharex=True)
    axes[0].plot(rel(t_cpu), cpu_used)
    axes[0].set_title("CPU used (%)")
    axes[1].plot(rel(t_ram), ram_used)
    axes[1].set_title("RAM used")
    axes[2].plot(rel(t_disk), disk_util)
    axes[2].set_title("Disk util")
    axes[3].plot(rel(t_net), net_rx, label="rx")
    axes[3].plot(rel(t_net), net_tx, label="tx")
    axes[3].legend()
    axes[3].set_title("Network")

    for ax in axes:
        for x, name in [(ready_epoch, "READY"), (load_start, "LOAD_START"), (load_end, "LOAD_END"), (end_epoch, "END")]:
            ax.axvline(x - start_epoch)
            ax.text(x - start_epoch, ax.get_ylim()[1], name, va="top", fontsize=8)

    axes[-1].set_xlabel("seconds since START")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "fig1_timeseries.png"), dpi=150)
    plt.close(fig)

    shutil.copy2(log_file, os.path.join(out_dir, "redacted.log"))

if __name__ == "__main__":
    main()
