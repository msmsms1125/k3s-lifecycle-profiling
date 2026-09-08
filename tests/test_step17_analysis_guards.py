from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "analysis" / "plot_step17_tinyllama_infer_load.py"
os.environ.setdefault(
    "MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "k3s-profile-matplotlib")
)


def load_module():
    spec = importlib.util.spec_from_file_location("plot_step17", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


analysis = load_module()


class Step17AnalysisGuardTests(unittest.TestCase):
    def test_series_is_sorted_and_duplicate_timestamp_keeps_last_value(self):
        frame = pd.DataFrame({"time": [3, 1, 2, 2]})
        timestamps, values = analysis.sorted_series(
            frame, [30, 10, 20, 22], "fixture"
        )
        np.testing.assert_array_equal(timestamps, [1.0, 2.0, 3.0])
        np.testing.assert_array_equal(values, [10.0, 22.0, 30.0])
        self.assertEqual(42.0, analysis.auc(timestamps, values))

    def test_utilization_outside_percentage_range_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside expected range"):
            analysis.validate_range(
                "CPU used percent",
                np.array([10.0, 101.0]),
                minimum=0.0,
                maximum=100.0,
            )

    def test_ambiguous_metric_column_is_rejected(self):
        frame = pd.DataFrame(
            {"time": [1, 2], "rx packets": [1, 2], "rx bytes": [3, 4]}
        )
        with self.assertRaisesRegex(ValueError, "unambiguous"):
            analysis.find_col(frame, ("rx",), "network receive")


if __name__ == "__main__":
    unittest.main()
