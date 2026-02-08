import re
import json
import csv
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

STEP = "step11_network"

PING_TIME_RE = re.compile(r"time=([0-9.]+)\s*ms")
PING_SUMMARY_RE = re.compile(r"(\d+)\s+packets transmitted,\s+(\d+)\s+received")

def parse_ping(path: Path):
    txt = path.read_text(errors="ignore").splitlines()

    rtts = []
    tx = rx = None

    for line in txt:
        m = PING_TIME_RE.search(line)
        if m:
            rtts.append(float(m.group(1)))

        m2 = PING_SUMMARY_RE.search(line)
        if m2:
            tx = int(m2.group(1))
            rx = int(m2.group(2))

    if tx is None or rx is None:
        # fallback: count reply lines
        rx = len([l for l in txt if "bytes from" in l])
        tx = rx

    loss_pct = 0.0 if tx == 0 else (tx - rx) * 100.0 / tx
    ping_mean = float(np.mean(rtts)) if rtts else float("nan")
    ping_p95 = float(np.percentile(rtts, 95)) if rtts else float("nan")

    return {
        "rtts": rtts,
        "ping_mean_ms": ping_mean,
        "ping_p95_ms": ping_p95,
        "loss_pct": loss_pct,
    }

def parse_iperf3_json(path: Path):
    obj = json.loads(path.read_text(errors="ignore"))

    bps_list = []
    for itv in obj.get("intervals", []):
        s = itv.get("sum")
        if s and "bits_per_second" in s:
            bps_list.append(float(s["bits_per_second"]))
            continue

        sr = itv.get("sum_received")
        if sr and "bits_per_second" in sr:
            bps_list.append(float(sr["bits_per_second"]))

    mbps = [v / 1e6 for v in bps_list]
    tcp_mean = float(np.mean(mbps)) if mbps else float("nan")
    tcp_peak = float(np.max(mbps)) if mbps else float("nan")

    return {
        "mbps_series": mbps,
        "tcp_mean_mbps": tcp_mean,
        "tcp_peak_mbps": tcp_peak,
    }

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def main():
    base_data = Path("data/network") / STEP
    base_results = Path("results") / STEP

    runs = sorted([p for p in base_data.glob("run_*") if p.is_dir()],
                  key=lambda x: int(x.name.split("_")[1]))

    if not runs:
        print(f"No runs found in {base_data}")
        return

    for run_dir in runs:
        run_idx = run_dir.name.split("_")[1]
        out_dir = base_results / f"run_{run_idx}"
        ensure_dir(out_dir)

        rows = []

        for ping_file in sorted(run_dir.glob("ping_master_to_*.txt")):
            name = ping_file.stem.replace("ping_master_to_", "")
            iperf_file = run_dir / f"iperf_master_to_{name}_tcp.json"

            if not iperf_file.exists():
                print(f"[WARN] missing iperf json: {iperf_file}")
                continue

            ping = parse_ping(ping_file)
            iperf = parse_iperf3_json(iperf_file)

            rows.append({
                "worker": name,
                "tcp_mean_mbps": iperf["tcp_mean_mbps"],
                "tcp_peak_mbps": iperf["tcp_peak_mbps"],
                "ping_mean_ms": ping["ping_mean_ms"],
                "ping_p95_ms": ping["ping_p95_ms"],
                "loss_pct": ping["loss_pct"],
            })

        stats_path = out_dir / "stats.csv"
        with stats_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=[
                "worker", "tcp_mean_mbps", "tcp_peak_mbps",
                "ping_mean_ms", "ping_p95_ms", "loss_pct"
            ])
            w.writeheader()
            for r in rows:
                w.writerow(r)

        plt.figure(figsize=(12, 7))

        ax1 = plt.subplot(2, 1, 1)
        for r in rows:
            name = r["worker"]
            iperf = parse_iperf3_json(run_dir / f"iperf_master_to_{name}_tcp.json")
            ax1.plot(iperf["mbps_series"], label=f"{name}")
        ax1.set_title(f"Run {run_idx} - iperf3 TCP Throughput (Mbps)")
        ax1.set_xlabel("interval index")
        ax1.set_ylabel("Mbps")
        ax1.legend()

        ax2 = plt.subplot(2, 1, 2)
        for r in rows:
            name = r["worker"]
            ping = parse_ping(run_dir / f"ping_master_to_{name}.txt")
            ax2.plot(ping["rtts"], label=f"{name}")
        ax2.set_title(f"Run {run_idx} - Ping RTT (ms)")
        ax2.set_xlabel("packet index")
        ax2.set_ylabel("ms")
        ax2.legend()

        plt.tight_layout()
        plt.savefig(out_dir / "fig1_network.png", dpi=200)
        plt.close()

        redacted_src = Path("logs/redacted") / STEP / f"run_{run_idx}.log"
        if redacted_src.exists():
            (out_dir / "redacted.log").write_text(redacted_src.read_text(errors="ignore"), errors="ignore")

        print(f"[OK] run_{run_idx}: stats.csv + fig1_network.png")

if __name__ == "__main__":
    main()
