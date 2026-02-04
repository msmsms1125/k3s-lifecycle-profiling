import csv
from pathlib import Path
import numpy as np

STEP = "step11_network"

def main():
    base = Path("results") / STEP
    run_dirs = sorted([p for p in base.glob("run_*") if p.is_dir()],
                      key=lambda x: int(x.name.split("_")[1]))

    out = base / "summary.csv"
    rows_out = []

    for rd in run_dirs:
        run_idx = int(rd.name.split("_")[1])
        stats = rd / "stats.csv"
        if not stats.exists():
            continue

        tcp_means, ping_means, ping_p95s, losses = [], [], [], []
        with stats.open() as f:
            r = csv.DictReader(f)
            for row in r:
                tcp_means.append(float(row["tcp_mean_mbps"]))
                ping_means.append(float(row["ping_mean_ms"]))
                ping_p95s.append(float(row["ping_p95_ms"]))
                losses.append(float(row["loss_pct"]))

        rows_out.append({
            "run": run_idx,
            "tcp_mean_mbps_avg_over_workers": float(np.mean(tcp_means)) if tcp_means else float("nan"),
            "ping_mean_ms_avg_over_workers": float(np.mean(ping_means)) if ping_means else float("nan"),
            "ping_p95_ms_avg_over_workers": float(np.mean(ping_p95s)) if ping_p95s else float("nan"),
            "loss_pct_avg_over_workers": float(np.mean(losses)) if losses else float("nan"),
        })

    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "run",
            "tcp_mean_mbps_avg_over_workers",
            "ping_mean_ms_avg_over_workers",
            "ping_p95_ms_avg_over_workers",
            "loss_pct_avg_over_workers",
        ])
        w.writeheader()
        for r in rows_out:
            w.writerow(r)

    print(f"[OK] wrote {out} ({len(rows_out)} runs)")

if __name__ == "__main__":
    main()
