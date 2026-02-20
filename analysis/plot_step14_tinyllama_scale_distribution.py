import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

STEP = "step14_scale_up_down_tinyllama_http"
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RESULT_BASE = os.path.join(BASE_DIR, "results", STEP)


def load_summary():
    path = os.path.join(RESULT_BASE, "summary.csv")
    if os.path.exists(path):
        return pd.read_csv(path)
    per_run = []
    for i in range(1, 11):
        p = os.path.join(RESULT_BASE, f"run_{i}", "stats.csv")
        if os.path.exists(p):
            per_run.append(pd.read_csv(p))
    if not per_run:
        return None
    return pd.concat(per_run, ignore_index=True)


def violin_or_box(ax, data, label, color):
    clean = [x for x in data if not np.isnan(x)]
    if len(clean) < 2:
        ax.bar([0], [clean[0]] if clean else [0], color=color, alpha=0.7, width=0.4)
    else:
        parts = ax.violinplot([clean], positions=[0], showmedians=True, showextrema=True)
        for pc in parts["bodies"]:
            pc.set_facecolor(color)
            pc.set_alpha(0.6)
        parts["cmedians"].set_color("black")
        parts["cmedians"].set_linewidth(2)
        ax.scatter([0] * len(clean), clean, color="black", s=20, zorder=3, alpha=0.7)
    mean_val = np.nanmean(data)
    std_val = np.nanstd(data)
    ax.set_title(f"{label}\n$\\mu$={mean_val:.1f} $\\sigma$={std_val:.1f}", fontsize=9)
    ax.set_xticks([])
    ax.grid(True, axis="y", alpha=0.3)


def main():
    df = load_summary()
    if df is None or df.empty:
        print("No summary data found. Run plot_step14_tinyllama_scale.py first.")
        sys.exit(1)

    metrics = [
        ("T_scale_up", "T_scale_up (s)", "tab:blue"),
        ("T_scale_down", "T_scale_down (s)", "tab:cyan"),
        ("T_total", "T_total (s)", "tab:orange"),
        ("cpu_mean", "CPU Mean (%)", "tab:green"),
        ("cpu_peak", "CPU Peak (%)", "tab:red"),
        ("ram_mean", "RAM Mean (MB)", "tab:purple"),
        ("ram_peak", "RAM Peak (MB)", "tab:pink"),
        ("disk_mean", "Disk Mean (%)", "tab:brown"),
        ("disk_peak", "Disk Peak (%)", "tab:gray"),
        ("net_rx_peak_kbps", "Net Rx Peak (KB/s)", "tab:olive"),
        ("net_tx_peak_kbps", "Net Tx Peak (KB/s)", "tab:orange"),
    ]

    available = [(col, label, color) for col, label, color in metrics if col in df.columns]
    n = len(available)
    cols = 5
    rows = (n + cols - 1) // cols

    fig = plt.figure(figsize=(cols * 3.2, rows * 3.5))
    gs = gridspec.GridSpec(rows, cols, figure=fig, hspace=0.7, wspace=0.4)

    for idx, (col, label, color) in enumerate(available):
        ax = fig.add_subplot(gs[idx // cols, idx % cols])
        data = df[col].values.astype(float)
        violin_or_box(ax, data, label, color)

    fig.suptitle(f"[{STEP}] Fig2 — Distribution over {len(df)} runs", fontsize=12, fontweight="bold", y=1.01)

    out_path = os.path.join(RESULT_BASE, "fig2_distribution.png")
    os.makedirs(RESULT_BASE, exist_ok=True)
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Fig2 saved: {out_path}")


if __name__ == "__main__":
    main()
