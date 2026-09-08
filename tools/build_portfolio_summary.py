#!/usr/bin/env python3
"""Build the portfolio timing summary from publishable event logs.

This script intentionally ignores the historical Netdata-derived resource
statistics. The source logs retain second-resolution lifecycle timestamps, so
those durations can still be independently summarized without the retired
Raspberry Pi cluster.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
import statistics
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = ROOT / "results" / "_summary" / "portfolio_event_timings.csv"
CHART_PATH = ROOT / "docs" / "assets" / "lifecycle-event-timings.png"
RUN_LOG = re.compile(r"run_(\d+)\.log$")
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault(
    "MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "k3s-profile-matplotlib")
)


@dataclass(frozen=True)
class SeriesSpec:
    phase: str
    scenario: str
    directory: str
    key: str


@dataclass(frozen=True)
class TimingSeries:
    spec: SeriesSpec
    values: tuple[float, ...]

    @property
    def mean(self) -> float:
        return statistics.mean(self.values)

    @property
    def median(self) -> float:
        return statistics.median(self.values)


SERIES = (
    SeriesSpec("A", "K3s master start to Ready", "step02_start_master", "T_READY_SEC"),
    SeriesSpec("A", "Nginx apply to rollout complete", "step04_apply_deployment", "T_total"),
    SeriesSpec("A", "Nginx scale down and up", "step06_scale_up_down", "T_total"),
    SeriesSpec("A", "Nginx rollout restart", "step07_rollout_restart", "T_total"),
    SeriesSpec("B", "TinyLlama scale 1 to 3 Ready", "step14_scale_up_down_tinyllama_http", "T_scale_up"),
    SeriesSpec("B", "TinyLlama scale 3 to 1 complete", "step14_scale_up_down_tinyllama_http", "T_scale_down"),
    SeriesSpec("B", "TinyLlama rollout restart to Ready", "step15_rollout_restart_tinyllama_http", "T_READY_SEC"),
)


def run_number(path: Path) -> int:
    match = RUN_LOG.fullmatch(path.name)
    if match is None:
        raise ValueError(f"Not a numbered run log: {path}")
    return int(match.group(1))


def parse_key_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = raw_line.partition("=")
        if separator:
            values[key.strip()] = value.strip()
    return values


def collect_series() -> list[TimingSeries]:
    collected: list[TimingSeries] = []
    log_root = ROOT / "logs" / "redacted"
    for spec in SERIES:
        paths = sorted(
            (path for path in (log_root / spec.directory).glob("run_*.log") if RUN_LOG.fullmatch(path.name)),
            key=run_number,
        )
        if len(paths) != 10:
            raise ValueError(
                f"{spec.directory}: expected 10 numbered run logs, found {len(paths)}"
            )

        values = []
        for path in paths:
            fields = parse_key_values(path)
            raw_value = fields.get(spec.key, "")
            if not raw_value:
                raise ValueError(f"{path.relative_to(ROOT)}: missing {spec.key}")
            value = float(raw_value)
            if value < 0:
                raise ValueError(f"{path.relative_to(ROOT)}: negative {spec.key}")
            values.append(value)
        collected.append(TimingSeries(spec, tuple(values)))
    return collected


def format_number(value: float) -> str:
    return f"{value:.1f}"


def build_csv(series: list[TimingSeries]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        (
            "phase",
            "scenario",
            "metric",
            "n",
            "mean_sec",
            "median_sec",
            "min_sec",
            "max_sec",
            "source",
        )
    )
    for item in series:
        writer.writerow(
            (
                item.spec.phase,
                item.spec.scenario,
                item.spec.key,
                len(item.values),
                format_number(item.mean),
                format_number(item.median),
                format_number(min(item.values)),
                format_number(max(item.values)),
                f"logs/redacted/{item.spec.directory}/run_*.log",
            )
        )
    return output.getvalue()


def render_chart(series: list[TimingSeries]) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    phase_titles = {
        "A": "Phase A - K3s lifecycle (master + 1 worker)",
        "B": "Phase B - TinyLlama lifecycle (master + 3 workers)",
    }
    colors = {"A": "#2563eb", "B": "#ea580c"}
    figure, axes = plt.subplots(1, 2, figsize=(16, 8))
    figure.subplots_adjust(left=0.21, right=0.97, bottom=0.20, top=0.82, wspace=1.00)

    for axis, phase in zip(axes, ("A", "B"), strict=True):
        items = [item for item in series if item.spec.phase == phase]
        for row, item in enumerate(items):
            color = colors[phase]
            low, high = min(item.values), max(item.values)
            offsets = [((index % 5) - 2) * 0.045 for index in range(len(item.values))]
            axis.hlines(row, low, high, color=color, linewidth=4, alpha=0.28)
            axis.scatter(
                item.values,
                [row + offset for offset in offsets],
                color=color,
                edgecolor="white",
                linewidth=0.7,
                s=42,
                zorder=3,
            )
            axis.vlines(item.median, row - 0.19, row + 0.19, color="#111827", linewidth=2)
            axis.scatter(
                [item.mean],
                [row],
                marker="D",
                color="#111827",
                edgecolor="white",
                linewidth=0.7,
                s=64,
                zorder=4,
            )
            axis.text(
                high + 0.8,
                row,
                f"mean {item.mean:.1f}s",
                va="center",
                fontsize=9,
                color="#374151",
            )

        axis.set_yticks(range(len(items)), [item.spec.scenario for item in items])
        axis.invert_yaxis()
        axis.set_title(phase_titles[phase], fontsize=12, fontweight="bold")
        axis.set_xlabel("Duration (seconds)")
        axis.set_xlim(0, max(max(item.values) for item in items) * 1.18 + 2)
        axis.grid(axis="x", color="#d1d5db", linewidth=0.8, alpha=0.8)
        axis.spines[["top", "right", "left"]].set_visible(False)
        axis.tick_params(axis="y", length=0)

    figure.suptitle(
        "Lifecycle event durations recomputed from preserved logs",
        fontsize=16,
        fontweight="bold",
    )
    legend = (
        Line2D([0], [0], marker="o", color="none", markerfacecolor="#64748b", label="individual run"),
        Line2D([0], [0], marker="|", color="#111827", markersize=14, label="median"),
        Line2D([0], [0], marker="D", color="none", markerfacecolor="#111827", label="mean"),
    )
    figure.legend(
        handles=legend,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.065),
        ncol=3,
        frameon=False,
    )
    figure.text(
        0.5,
        0.025,
        "n=10 per metric. Event timestamps have 1-second resolution; resource metrics are excluded.",
        ha="center",
        fontsize=9,
        color="#4b5563",
    )
    CHART_PATH.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(CHART_PATH, dpi=160, bbox_inches="tight", metadata={"Software": "Matplotlib"})
    plt.close(figure)


def check_outputs(expected_csv: str) -> int:
    failures = []
    if not SUMMARY_PATH.exists():
        failures.append(f"missing {SUMMARY_PATH.relative_to(ROOT)}")
    elif SUMMARY_PATH.read_text(encoding="utf-8") != expected_csv:
        failures.append(f"stale {SUMMARY_PATH.relative_to(ROOT)}")
    if not CHART_PATH.is_file() or CHART_PATH.stat().st_size == 0:
        failures.append(f"missing {CHART_PATH.relative_to(ROOT)}")

    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
        return 1
    print("[OK] Portfolio summary matches 70 timing observations from 60 event logs")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify that tracked portfolio outputs match the preserved logs",
    )
    args = parser.parse_args()

    try:
        series = collect_series()
        summary_csv = build_csv(series)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"[FAIL] {exc}")
        return 1

    if args.check:
        return check_outputs(summary_csv)

    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(summary_csv, encoding="utf-8")
    render_chart(series)
    print(f"Wrote {SUMMARY_PATH.relative_to(ROOT)}")
    print(f"Wrote {CHART_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
