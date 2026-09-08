from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "build_portfolio_summary.py"


def load_module():
    spec = importlib.util.spec_from_file_location("build_portfolio_summary", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


portfolio = load_module()


class PortfolioSummaryTests(unittest.TestCase):
    def test_recomputes_expected_statistics_from_70_timing_observations(self):
        series = portfolio.collect_series()
        by_name = {item.spec.scenario: item for item in series}

        self.assertEqual(7, len(series))
        self.assertTrue(all(len(item.values) == 10 for item in series))
        self.assertEqual(13.7, by_name["K3s master start to Ready"].mean)
        self.assertEqual(9.0, by_name["Nginx rollout restart"].median)
        self.assertEqual(43.6, by_name["TinyLlama scale 1 to 3 Ready"].mean)

    def test_tracked_csv_matches_preserved_logs(self):
        expected = portfolio.build_csv(portfolio.collect_series())
        actual = portfolio.SUMMARY_PATH.read_text(encoding="utf-8")
        self.assertEqual(expected, actual)


if __name__ == "__main__":
    unittest.main()
