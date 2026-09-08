#!/usr/bin/env python3
"""Offline quality gate for this repository.

The checks deliberately avoid a live K3s cluster. They validate the material that
can still be verified after the original Raspberry Pi testbed was retired.
"""

from __future__ import annotations

import ipaddress
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ("analysis", "scripts", "docker", "tools", "tests")
EXPECTED_STEPS = (
    "step01_system_idle",
    "step02_start_master",
    "step03_cluster_idle",
    "step04_apply_deployment",
    "step05_deployment_idle",
    "step06_scale_up_down",
    "step07_rollout_restart",
    "step08_cordon_uncordon",
    "step09_stop_final_idle",
    "step10_delete_deployment",
    "step11_network",
    "step12_apply_tinyllama_http",
    "step13_tinyllama_idle",
    "step14_scale_up_down_tinyllama_http",
    "step15_rollout_restart_tinyllama_http",
    "step16_delete_tinyllama_http_deployment",
    "step17_infer_load_1rps_tinyllama_http",
)
REQUIRED_PACKAGES = {"matplotlib", "numpy", "pandas", "requests", "seaborn"}
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
HOME_PATH = re.compile(r"(?:/home/[^/\s]+|[A-Za-z]:\\Users\\[^\\\s]+)")
SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?:api[_-]?key|password|secret|token)\s*[:=]\s*(?!<redacted>)[^\s]{8,}"
)
PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def ok(self, message: str) -> None:
        print(f"[OK] {message}")

    def fail(self, message: str) -> None:
        self.failures.append(message)
        print(f"[FAIL] {message}")


def source_files(suffix: str):
    for directory in SOURCE_DIRS:
        root = ROOT / directory
        if root.exists():
            yield from root.rglob(f"*{suffix}")


def check_python_syntax(report: Report) -> None:
    files = sorted(source_files(".py"))
    for path in files:
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except (OSError, SyntaxError, UnicodeError) as exc:
            report.fail(f"Python syntax: {path.relative_to(ROOT)}: {exc}")
    if not any(item.startswith("Python syntax:") for item in report.failures):
        report.ok(f"Python syntax ({len(files)} files)")


def link_target(markdown: Path, raw_target: str) -> Path | None:
    target = raw_target.strip().strip("<>").split(maxsplit=1)[0]
    if not target or target.startswith(("#", "http://", "https://", "mailto:")):
        return None
    target = unquote(target.split("#", 1)[0])
    return (markdown.parent / target).resolve()


def check_markdown_links(report: Report) -> None:
    markdown_files = sorted(
        path for path in ROOT.rglob("*.md") if ".git" not in path.parts
    )
    checked = 0
    failures_before = len(report.failures)
    for markdown in markdown_files:
        text = markdown.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(text):
            target = link_target(markdown, match.group(1))
            if target is None:
                continue
            checked += 1
            try:
                target.relative_to(ROOT)
            except ValueError:
                report.fail(
                    f"Markdown link escapes repository in {markdown.relative_to(ROOT)}: "
                    f"{match.group(1)}"
                )
                continue
            if not target.exists():
                report.fail(
                    f"Broken Markdown link in {markdown.relative_to(ROOT)}: "
                    f"{match.group(1)}"
                )
    if len(report.failures) == failures_before:
        report.ok(f"Local Markdown links ({checked} links)")


def check_step_layout(report: Report) -> None:
    failures_before = len(report.failures)
    for step in EXPECTED_STEPS:
        for top_level in ("scripts", "results"):
            path = ROOT / top_level / step
            if not path.is_dir():
                report.fail(f"Missing {top_level} directory: {path.relative_to(ROOT)}")
    if len(report.failures) == failures_before:
        report.ok(f"Experiment layout ({len(EXPECTED_STEPS)} steps)")


def check_requirements(report: Report) -> None:
    path = ROOT / "requirements.txt"
    packages = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        packages.add(re.split(r"[<>=!~\[]", line, maxsplit=1)[0].lower())
    missing = sorted(REQUIRED_PACKAGES - packages)
    if missing:
        report.fail(f"requirements.txt is missing: {', '.join(missing)}")
    else:
        report.ok("Declared Python runtime dependencies")


def check_prompt_fixture(report: Report) -> None:
    path = ROOT / "scripts" / EXPECTED_STEPS[-1] / "prompts_60.txt"
    counts: Counter[str] = Counter()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        group, separator, prompt = raw_line.partition("\t")
        if separator and prompt.strip():
            counts[group.strip().lower()] += 1
    expected = {"short": 20, "medium": 20, "long": 20}
    if dict(counts) != expected:
        report.fail(f"Step17 prompt groups must be {expected}, got {dict(counts)}")
    else:
        report.ok("Step17 prompt fixture (20 short / 20 medium / 20 long)")


def is_rfc1918(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return any(address in network for network in PRIVATE_NETWORKS)


def check_publishable_logs(report: Report) -> None:
    root = ROOT / "logs" / "redacted"
    files = sorted(path for path in root.rglob("*") if path.is_file())
    failures_before = len(report.failures)
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            report.fail(f"Non-UTF-8 publishable log: {path.relative_to(ROOT)}")
            continue
        findings = []
        if HOME_PATH.search(text):
            findings.append("absolute user home path")
        private_ips = sorted({value for value in IPV4.findall(text) if is_rfc1918(value)})
        if private_ips:
            findings.append("RFC1918 address")
        if SECRET_ASSIGNMENT.search(text):
            findings.append("secret-like assignment")
        if findings:
            report.fail(
                f"Redaction regression in {path.relative_to(ROOT)}: {', '.join(findings)}"
            )
    if len(report.failures) == failures_before:
        report.ok(f"Publishable-log redaction ({len(files)} files)")


def print_artifact_inventory() -> None:
    print("\nArtifact inventory (presence only; not a validity claim):")
    print("step  result_files  log_files")
    for step in EXPECTED_STEPS:
        result_root = ROOT / "results" / step
        log_root = ROOT / "logs" / "redacted" / step
        result_files = sum(path.is_file() for path in result_root.rglob("*"))
        log_files = sum(path.is_file() for path in log_root.rglob("*")) if log_root.exists() else 0
        print(f"{step[:6]:<6}{result_files:>14}{log_files:>11}")


def main() -> int:
    report = Report()
    check_python_syntax(report)
    check_markdown_links(report)
    check_step_layout(report)
    check_requirements(report)
    check_prompt_fixture(report)
    check_publishable_logs(report)
    print_artifact_inventory()

    if report.failures:
        print(f"\nRepository verification failed ({len(report.failures)} issue(s)).")
        return 1
    print("\nRepository verification passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
