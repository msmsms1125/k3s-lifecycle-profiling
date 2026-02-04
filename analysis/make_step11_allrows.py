import csv
from pathlib import Path

STEP = "step11_network"

def main():
    base = Path("results") / STEP
    run_dirs = sorted([p for p in base.glob("run_*") if p.is_dir()],
                      key=lambda x: int(x.name.split("_")[1]))

    out_path = base / "all_runs_workers.csv"
    rows = []

    for rd in run_dirs:
        run_idx = int(rd.name.split("_")[1])
        stats = rd / "stats.csv"
        if not stats.exists():
            continue

        with stats.open() as f:
            r = csv.DictReader(f)
            for row in r:
                rows.append({
                    "run": run_idx,
                    "worker": row["worker"],
                    "tcp_mean_mbps": row["tcp_mean_mbps"],
                    "tcp_peak_mbps": row["tcp_peak_mbps"],
                    "ping_mean_ms": row["ping_mean_ms"],
                    "ping_p95_ms": row["ping_p95_ms"],
                    "loss_pct": row["loss_pct"],
                })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "run","worker",
            "tcp_mean_mbps","tcp_peak_mbps",
            "ping_mean_ms","ping_p95_ms","loss_pct"
        ])
        w.writeheader()
        for row in rows:
            w.writerow(row)

    print(f"[OK] wrote {out_path} ({len(rows)} rows)")

if __name__ == "__main__":
    main()
