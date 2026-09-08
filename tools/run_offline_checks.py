#!/usr/bin/env python3
"""Run every hardware-independent quality check from one entry point.

This command intentionally does not contact a K3s cluster or regenerate benchmark
claims. It only verifies source code and the publishable artifacts already stored
in the repository.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]


def run_check(
    label: str,
    command: Sequence[str],
    *,
    extra_env: dict[str, str] | None = None,
) -> bool:
    """Run one check, stream its output, and return whether it passed."""

    print(f"\n==> {label}", flush=True)
    environment = os.environ.copy()
    if extra_env:
        environment.update(extra_env)
    completed = subprocess.run(command, cwd=ROOT, env=environment, check=False)
    if completed.returncode == 0:
        print(f"[PASS] {label}")
        return True
    print(f"[FAIL] {label} (exit {completed.returncode})")
    return False


def find_bash(explicit: str | None) -> str | None:
    """Prefer Git Bash on Windows, then fall back to PATH lookup."""

    if explicit:
        candidate = Path(explicit).expanduser()
        if candidate.is_file():
            return str(candidate)
        return shutil.which(explicit)

    candidates: list[Path] = []
    if os.name == "nt":
        for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(variable)
            if not base:
                continue
            root = Path(base)
            if variable == "LOCALAPPDATA":
                candidates.append(root / "Programs" / "Git" / "bin" / "bash.exe")
            else:
                candidates.extend(
                    (root / "Git" / "bin" / "bash.exe", root / "Git" / "usr" / "bin" / "bash.exe")
                )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which("bash")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run checks that do not require the retired Raspberry Pi testbed."
    )
    shell_group = parser.add_mutually_exclusive_group()
    shell_group.add_argument(
        "--skip-shell-syntax",
        action="store_true",
        help="skip bash -n validation even when Bash is available",
    )
    shell_group.add_argument(
        "--require-shell-syntax",
        action="store_true",
        help="fail instead of skipping when Bash is unavailable (used by CI)",
    )
    parser.add_argument(
        "--bash",
        metavar="PATH",
        help="explicit Bash executable for shell syntax validation",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    python = sys.executable
    results = [
        run_check(
            "Repository structure, links, dependencies, and redaction",
            [python, "tools/verify_repository.py"],
        ),
        run_check(
            "Portfolio evidence summary matches preserved event logs",
            [python, "tools/build_portfolio_summary.py", "--check"],
        ),
        run_check(
            "Offline regression tests",
            [python, "-m", "unittest", "discover", "-s", "tests", "-v"],
            extra_env={"MPLBACKEND": "Agg"},
        ),
    ]

    shell_status = "skipped by option"
    if not args.skip_shell_syntax:
        bash = find_bash(args.bash)
        if bash:
            shell_files = sorted(
                path.relative_to(ROOT).as_posix()
                for path in (ROOT / "scripts").rglob("*.sh")
            )
            results.append(
                run_check(
                    f"Shell syntax ({len(shell_files)} scripts)",
                    [bash, "-n", *shell_files],
                )
            )
            shell_status = "checked"
        elif args.require_shell_syntax:
            print("\n[FAIL] Shell syntax: Bash executable not found")
            results.append(False)
            shell_status = "required but unavailable"
        else:
            shell_status = "skipped because Bash is unavailable"

    passed = sum(results)
    print(f"\nOffline quality summary: {passed}/{len(results)} checks passed")
    print(f"Shell syntax: {shell_status}")
    if all(results):
        print("No live cluster or new benchmark run was used.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
