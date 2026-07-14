from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from garfield_bench.report import write_reports


class ReportTests(unittest.TestCase):
    def test_report_aggregates_tree_tokens_and_amortization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root / "runs"
            for treatment, root_tokens, child_tokens, cached_tokens in (
                ("garfield", 100, 50, 80),
                ("swamp-garfield", 70, 40, 60),
            ):
                run = runs / f"contained-r01-{treatment}"
                run.mkdir(parents=True)
                (run / "result.json").write_text(
                    json.dumps(
                        {
                            "run_id": run.name,
                            "case_id": "contained",
                            "treatment": treatment,
                            "duration_ms": 1000,
                        }
                    )
                )
                (run / "grading.json").write_text(json.dumps({"passed": True}))
                usage = [
                    {
                        "total_tokens": root_tokens,
                        "input_tokens": root_tokens - 10,
                        "cached_input_tokens": cached_tokens,
                        "output_tokens": 10,
                        "parent_agent_id": None,
                    },
                    {
                        "total_tokens": child_tokens,
                        "input_tokens": child_tokens - 5,
                        "cached_input_tokens": 10,
                        "output_tokens": 5,
                        "parent_agent_id": "root",
                    },
                ]
                (run / "usage.jsonl").write_text("\n".join(json.dumps(row) for row in usage) + "\n")

            report = write_reports(runs, root / "report", factory_authoring_tokens=500)
            self.assertEqual(report["run_count"], 2)
            self.assertEqual(len(report["amortization"]), 5)
            garfield = next(group for group in report["groups"] if group["treatment"] == "garfield")
            self.assertEqual(garfield["median_cached_input_tokens"], 90)
            self.assertEqual(garfield["median_uncached_input_tokens"], 45)
            self.assertEqual(garfield["median_output_tokens"], 15)
            self.assertTrue((root / "report" / "report.html").exists())


if __name__ == "__main__":
    unittest.main()
