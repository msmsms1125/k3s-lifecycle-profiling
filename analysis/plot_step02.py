import sys
from pathlib import Path
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


EPOCH_RE = re.compile(r'^(START_EPOCH|READY_EPOCH|END_EPOCH)=(\d+)\s*$')

def parse_epochs(log_path: Path):
    epochs = {"START_EPOCH": None, "READY_EPOCH": None, "END_EPOCH": None}
    if not log_path.exists():
        return epochs
    for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = EPOCH_RE.match(line.strip())
        if m:
            epochs[m.group(1)] = int(m.group(2))
    return epochs


def load_df(p: Path) -> pd.DataFrame:
    df = pd.read_csv(p)
    if "time" not in df.columns:
        # netdata가 time 대신 첫 컬럼으로 주는 경우 방어
        df = df.rename(columns={df.columns[0]: "time"})
    if pd.api.types.is_numeric_dtype(df["time"]):
        df["dt"] = pd.to_datetime(df["time"], unit="s")
    else:
        df["dt"] = pd.to_datetime(df["time"])
    return df.sort_values("dt").reset_index(drop=True)


def auc(series: pd.Series, dt: pd.Series) -> float:
    # numpy trapz deprecated 대응
    t = (dt - dt.iloc[0]).dt.total_seconds().to_numpy()
    y = series.to_numpy(dtype=float)
    return float(np.trapezoid(y, t))


def pick_cpu_total(cpu: pd.DataFrame) -> pd.Series:
    cols = cpu.columns
    if "user" in cols and "system" in cols:
        iow = cpu["iowait"] if "iowait" in cols else 0
        return cpu["user"].astype(float) + cpu["system"].astype(float) + pd.Series(iow).astype(float)
    if "idle" in cols:
        return 100.0 - cpu["idle"].astype(float)
    cand = [c for c in cols if c not in ("time", "dt")]
    if not cand:
        raise ValueError("CPU csv has no data columns")
    return cpu[cand[0]].astype(float)


def pick_ram_used(ram: pd.DataFrame) -> pd.Series:
    if "used" in ram.columns:
        return ram["used"].astype(float)
    cols = [c for c in ram.columns if c not in ("time", "dt")]
    if not cols:
        raise ValueError("RAM csv has no data columns")
    return ram[cols[0]].astype(float)


def pick_disk_util(du: pd.DataFrame) -> pd.Series:
    for c in ["utilization", "util", "busy"]:
        if c in du.columns:
            return du[c].astype(float)
    cols = [c for c in du.columns if c not in ("time", "dt")]
    if not cols:
        raise ValueError("disk util csv has no data columns")
    return du[cols[0]].astype(float)


def pick_reads_writes(dio: pd.DataFrame):
    cols = dio.columns
    if "reads" in cols and "writes" in cols:
        r = dio["reads"].astype(float).abs()
        w = dio["writes"].astype(float).abs()
        return r, w
    if "read" in cols and "write" in cols:
        r = dio["read"].astype(float).abs()
        w = dio["write"].astype(float).abs()
        return r, w
    cand = [c for c in cols if c not in ("time", "dt")]
    if not cand:
        raise ValueError("disk io csv has no data columns")
    r = dio[cand[0]].astype(float).abs()
    w = pd.Series(np.zeros(len(dio)), index=dio.index)
    return r, w


def clip_by_epochs(df: pd.DataFrame, start_epoch: int, end_epoch: int) -> pd.DataFrame:
    t0 = pd.to_datetime(start_epoch, unit="s")
    t1 = pd.to_datetime(end_epoch, unit="s")
    m = (df["dt"] >= t0) & (df["dt"] <= t1)
    out = df.loc[m].copy()
    return out if len(out) >= 3 else df


def save_stats_csv(path: Path, d: dict):
    df = pd.DataFrame([d])
    df.to_csv(path, index=False)


def main(step_dir="data/netdata/step02_start_master",
         log_dir="logs/redacted/step02_start_master",
         out_dir="results/step02_start_master"):

    step = Path(step_dir)
    logs = Path(log_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    run_dirs = sorted(
        [p for p in step.iterdir() if p.is_dir() and p.name.startswith("run_")],
        key=lambda x: int(x.name.split("_")[1])
    )

    rows_summary = []

    for run in run_dirs:
        cpu_p = run / "system_cpu.csv"
        ram_p = run / "system_ram.csv"
        du_ps = sorted(run.glob("disk_util_*.csv"))
        dio_ps = sorted(run.glob("disk_io_*.csv"))
        if not cpu_p.exists() or not ram_p.exists() or not du_ps or not dio_ps:
            raise FileNotFoundError(f"missing csv in {run}")

        du_p = du_ps[0]
        dio_p = dio_ps[0]

        cpu = load_df(cpu_p)
        ram = load_df(ram_p)
        du  = load_df(du_p)
        dio = load_df(dio_p)

        cpu_total = pick_cpu_total(cpu)
        ram_used  = pick_ram_used(ram)
        disk_util = pick_disk_util(du)
        reads, writes = pick_reads_writes(dio)

        ep = parse_epochs(logs / f"{run.name}.log")
        start_e = ep["START_EPOCH"]
        ready_e = ep["READY_EPOCH"]
        end_e   = ep["END_EPOCH"]
        if start_e is None or end_e is None:
            raise ValueError(f"missing START/END in log: {logs/run.name}.log")

        cpu_s = clip_by_epochs(cpu, start_e, end_e)
        ram_s = clip_by_epochs(ram, start_e, end_e)
        du_s  = clip_by_epochs(du,  start_e, end_e)
        dio_s = clip_by_epochs(dio, start_e, end_e)

        cpu_total_s = pick_cpu_total(cpu_s)
        ram_used_s  = pick_ram_used(ram_s)
        disk_util_s = pick_disk_util(du_s)
        reads_s, writes_s = pick_reads_writes(dio_s)

        run_out = out / run.name
        run_out.mkdir(parents=True, exist_ok=True)

        fig, ax = plt.subplots(3, 1, figsize=(11, 7), sharex=True)
        ax[0].plot(cpu["dt"], cpu_total); ax[0].set_ylabel("CPU %")
        ax[1].plot(ram["dt"], ram_used);  ax[1].set_ylabel("RAM used")
        ax[2].plot(du["dt"],  disk_util); ax[2].set_ylabel("Disk util %"); ax[2].set_xlabel("time")
        fig.suptitle(f"step02 start_master - {run.name}")
        fig.tight_layout()
        fig.savefig(run_out / "fig1_timeseries_cpu_ram_disk.png", dpi=200)
        plt.close(fig)

        fig = plt.figure(figsize=(11, 4))
        plt.plot(dio["dt"], reads, label="reads")
        plt.plot(dio["dt"], writes, label="writes")
        plt.xlabel("time"); plt.ylabel("KB/s (abs)"); plt.title(f"step02 start_master - {run.name} - disk IO")
        plt.legend(); plt.tight_layout()
        plt.savefig(run_out / "fig1_timeseries_disk_io.png", dpi=200)
        plt.close(fig)

        fig, ax = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
        ax[0].plot(cpu["dt"], cpu_total, label="CPU%")
        ax[0].plot(ram["dt"], ram_used, label="RAM")
        ax[0].plot(du["dt"],  disk_util, label="Disk util%")
        ax[0].legend()
        ax[0].set_ylabel("value")
        ax[0].set_title(f"step02 start_master - {run.name} (with epochs)")

        ax[1].plot(dio["dt"], reads, label="reads")
        ax[1].plot(dio["dt"], writes, label="writes")
        ax[1].legend()
        ax[1].set_ylabel("KB/s"); ax[1].set_xlabel("time")

        t_start = pd.to_datetime(start_e, unit="s")
        t_ready = pd.to_datetime(ready_e, unit="s") if ready_e is not None else None
        t_end   = pd.to_datetime(end_e, unit="s")

        for a in ax:
            a.axvline(t_start, linestyle="--", linewidth=1, label="START")
            if t_ready is not None:
                a.axvline(t_ready, linestyle="--", linewidth=1, label="READY")
            a.axvline(t_end, linestyle="--", linewidth=1, label="END")

        fig.tight_layout()
        fig.savefig(run_out / "plot.png", dpi=200)
        plt.close(fig)

        t_ready_sec = (ready_e - start_e) if ready_e is not None else np.nan
        t_total_sec = (end_e - start_e)

        stats = {
            "run": run.name,
            "start_epoch": start_e,
            "ready_epoch": ready_e,
            "end_epoch": end_e,
            "t_ready_sec": t_ready_sec,
            "t_total_sec": t_total_sec,

            "cpu_mean": float(cpu_total_s.mean()),
            "cpu_peak": float(cpu_total_s.max()),
            "cpu_auc":  auc(cpu_total_s, cpu_s["dt"]),

            "ram_mean": float(ram_used_s.mean()),
            "ram_peak": float(ram_used_s.max()),
            "ram_auc":  auc(ram_used_s, ram_s["dt"]),

            "disk_util_mean": float(disk_util_s.mean()),
            "disk_util_peak": float(disk_util_s.max()),
            "disk_util_auc":  auc(disk_util_s, du_s["dt"]),

            "disk_read_mean": float(reads_s.mean()),
            "disk_read_peak": float(reads_s.max()),
            "disk_read_auc":  auc(reads_s, dio_s["dt"]),

            "disk_write_mean": float(writes_s.mean()),
            "disk_write_peak": float(writes_s.max()),
            "disk_write_auc":  auc(writes_s, dio_s["dt"]),
        }
        save_stats_csv(run_out / "stats.csv", stats)

        rows_summary.append(stats)

    df = pd.DataFrame(rows_summary).sort_values(
        "run", key=lambda s: s.str.split("_").str[1].astype(int)
    )
    df.to_csv(out / "summary_step02.csv", index=False)

    def save_box(col: str, title: str, fname: str):
        fig = plt.figure(figsize=(7, 4))
        plt.boxplot(df[col].dropna(), tick_labels=[col], showmeans=True)
        plt.title(title); plt.tight_layout()
        plt.savefig(out / fname, dpi=200)
        plt.close(fig)

    save_box("t_ready_sec", "Fig2 - T_ready distribution (step02)", "fig2_t_ready_box.png")
    save_box("t_total_sec", "Fig2 - T_total distribution (step02)", "fig2_t_total_box.png")
    save_box("cpu_mean", "Fig2 - CPU mean distribution (step02)", "fig2_cpu_mean_box.png")
    save_box("ram_mean", "Fig2 - RAM used mean distribution (step02)", "fig2_ram_mean_box.png")
    save_box("disk_util_mean", "Fig2 - Disk util mean distribution (step02)", "fig2_disk_util_mean_box.png")

    print("Saved:", out / "summary_step02.csv")
    print("Per-run:", "fig1_*.png + plot.png + stats.csv under", out / "run_*")


if __name__ == "__main__":
    main(*sys.argv[1:])
