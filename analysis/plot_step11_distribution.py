import csv
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

STEP = "step11_network"

METRICS = [
    ("tcp_mean_mbps", "iperf3 TCP Mean (Mbps)"),
    ("tcp_peak_mbps", "iperf3 TCP Peak (Mbps)"),
    ("ping_mean_ms", "Ping Mean (ms)"),
    ("ping_p95_ms", "Ping p95 (ms)"),
    ("loss_pct", "Ping Loss (%)"),
]

def main():
    base = Path("results") / STEP
    allrows = base / "all_runs_workers.csv"
    if not allrows.exists():
        print(f"[ERR] missing {allrows}. Run make_step11_allrows.py first.")
        return

    data = {}
    with allrows.open() as f:
        r = csv.DictReader(f)
        for row in r:
            w = row["worker"]
            data.setdefault(w, {})
            for m, _ in METRICS:
                data[w].setdefault(m, [])
                try:
                    data[w][m].append(float(row[m]))
                except:
                    pass

    workers = sorted(data.keys())

    fig = plt.figure(figsize=(14, 10))

    for i, (m, title) in enumerate(METRICS, start=1):
        ax = plt.subplot(3, 2, i)

        series = [data[w].get(m, []) for w in workers]
        ax.boxplot(series, labels=workers, showmeans=True)

        ax.set_title(title)
        ax.set_xlabel("worker")
        ax.set_ylabel(m)

    plt.tight_layout()
    out = base / "fig2_distribution.png"
    plt.savefig(out, dpi=200)
    plt.close()
    print(f"[OK] wrote {out}")

if __name__ == "__main__":
    main()
