import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

def load_df(p: Path) -> pd.DataFrame:
    df = pd.read_csv(p)
    if "time" not in df.columns:
        raise ValueError(f"missing time column: {p}")
    if pd.api.types.is_numeric_dtype(df["time"]):
        df["dt"] = pd.to_datetime(df["time"], unit="s")
    else:
        df["dt"] = pd.to_datetime(df["time"])
    return df.sort_values("dt")

def auc(series: pd.Series, dt: pd.Series) -> float:
    t = (dt - dt.iloc[0]).dt.total_seconds().to_numpy()
    y = series.to_numpy(dtype=float)
    return float(np.trapz(y, t))

def pick_ram_used(ram: pd.DataFrame) -> pd.Series:
    if "used" in ram.columns:
        return ram["used"].astype(float)
    cols = [c for c in ram.columns if c not in ("time", "dt")]
    if not cols:
        raise ValueError("RAM csv has no data columns")
    return ram[cols[0]].astype(float)

def parse_kv_log(p: Path) -> dict:
    d = {}
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or "=" not in line: 
            continue
        k,v = line.split("=",1)
        d[k.strip()] = v.strip()
    return d

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", required=True)
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args()

    repo = Path(args.repo_root).resolve()
    step = args.step
    log_dir = repo / "logs" / "redacted" / step
    data_dir = repo / "data" / "netdata" / step
    out_dir  = repo / "results" / step
    out_dir.mkdir(parents=True, exist_ok=True)

    logs = sorted(log_dir.glob("run_*.log"), key=lambda p: int(p.stem.split("_")[1]))
    rows = []

    for logp in logs:
        run = int(logp.stem.split("_")[1])
        run_name = f"run_{run}"
        kv = parse_kv_log(logp)

        START = int(kv["START_EPOCH"])
        END   = int(kv["END_EPOCH"]) if kv.get("END_EPOCH") else START
        T_total = float(kv.get("T_total",""))

        rd = data_dir / run_name
        cpu = load_df(rd / "system_cpu.csv")
        ram = load_df(rd / "system_ram.csv")
        du  = load_df(rd / "disk_util_mmcblk0.csv")
        dio = load_df(rd / "disk_io_mmcblk0.csv")

        cpu_total = cpu["user"].astype(float) + cpu["system"].astype(float) + cpu.get("iowait", 0).astype(float)
        ram_used  = pick_ram_used(ram)
        disk_util = du["utilization"].astype(float) if "utilization" in du.columns else du[[c for c in du.columns if c not in ("time","dt")][0]].astype(float)
        reads  = dio["reads"].astype(float).abs() if "reads" in dio.columns else None
        writes = dio["writes"].astype(float).abs() if "writes" in dio.columns else None

        run_out = out_dir / run_name
        run_out.mkdir(parents=True, exist_ok=True)

        fig, ax = plt.subplots(4, 1, figsize=(12, 9), sharex=True)
        ax[0].plot(cpu["dt"], cpu_total); ax[0].set_ylabel("CPU %")
        ax[1].plot(ram["dt"], ram_used);  ax[1].set_ylabel("RAM used (MB)")
        ax[2].plot(du["dt"],  disk_util); ax[2].set_ylabel("Disk util %")
        if reads is not None and writes is not None:
            ax[3].plot(dio["dt"], reads,  label="reads")
            ax[3].plot(dio["dt"], writes, label="writes")
            ax[3].legend()
        ax[3].set_ylabel("IO (KB/s)")
        ax[3].set_xlabel("time")

        sdt = pd.to_datetime(START, unit="s")
        edt = pd.to_datetime(END,   unit="s")
        for a in ax:
            a.axvline(sdt, linestyle="--", linewidth=1); a.text(sdt, a.get_ylim()[1], " START", rotation=90, va="top")
            a.axvline(edt, linestyle="--", linewidth=1); a.text(edt, a.get_ylim()[1], " END",   rotation=90, va="top")

        fig.suptitle(f"{step} - {run_name} (stop then 60s observe)")
        fig.tight_layout()
        fig.savefig(run_out / "fig1_timeseries.png", dpi=200)
        plt.close(fig)

        row = {
            "step": step, "run": run,
            "START_EPOCH": START, "READY_EPOCH": "", "END_EPOCH": END,
            "T_ready": "", "T_total": T_total,

            "cpu_mean": float(cpu_total.mean()),
            "cpu_peak": float(cpu_total.max()),
            "cpu_auc":  auc(cpu_total, cpu["dt"]),

            "ram_mean": float(ram_used.mean()),
            "ram_peak": float(ram_used.max()),
            "ram_auc":  auc(ram_used, ram["dt"]),

            "disk_util_mean": float(disk_util.mean()),
            "disk_util_peak": float(disk_util.max()),
            "disk_util_auc":  auc(disk_util, du["dt"]),

            "disk_io_read_mean": float(reads.mean()) if reads is not None else np.nan,
            "disk_io_read_peak": float(reads.max()) if reads is not None else np.nan,
            "disk_io_read_auc":  auc(reads, dio["dt"]) if reads is not None else np.nan,

            "disk_io_write_mean": float(writes.mean()) if writes is not None else np.nan,
            "disk_io_write_peak": float(writes.max()) if writes is not None else np.nan,
            "disk_io_write_auc":  auc(writes, dio["dt"]) if writes is not None else np.nan,
        }
        pd.DataFrame([row]).to_csv(run_out / "stats.csv", index=False)
        (run_out / "redacted.log").write_text(logp.read_text())
        rows.append(row)

    df = pd.DataFrame(rows).sort_values("run")
    df.to_csv(out_dir / "summary.csv", index=False)

    metrics = ["cpu_mean","cpu_peak","ram_mean","disk_util_mean","T_total"]
    metrics = [m for m in metrics if m in df.columns]
    fig = plt.figure(figsize=(12, 5))
    plt.boxplot([df[m].dropna().to_numpy() for m in metrics], labels=metrics)
    plt.title(f"{step} - Fig2 distribution")
    plt.tight_layout()
    plt.savefig(out_dir / "fig2_distribution.png", dpi=200)
    plt.close(fig)

    print("Saved:", out_dir / "summary.csv")
    print("Saved:", out_dir / "fig2_distribution.png")

if __name__ == "__main__":
    main()
