from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from garfield_bench.adapters.base import AdapterConfig
from garfield_bench.runner import BenchmarkRunner


class RunnerSourceTests(unittest.TestCase):
    def test_treatments_use_their_own_source_repositories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calibration = root / "calibration.json"
            calibration.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "sessions": [
                            {"parent_agent_id": None},
                            {"parent_agent_id": "root"},
                        ],
                    }
                )
            )
            agents = root / "agents"
            extension = root / "garfield-extension"
            runner = BenchmarkRunner(
                base=root / "base",
                agents_repo=agents,
                extension_repo=extension,
                runs_root=root / "runs",
                calibration=calibration,
                adapter_config=AdapterConfig(),
                seed=1,
            )

            self.assertEqual(runner._control_source("garfield"), agents.resolve())
            self.assertEqual(runner._control_source("swamp-garfield"), agents.resolve())
            self.assertEqual(runner._control_source("workflow-garfield"), extension.resolve())

    def test_workflow_treatment_does_not_require_agents_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calibration = root / "calibration.json"
            calibration.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "sessions": [
                            {"parent_agent_id": None},
                            {"parent_agent_id": "root"},
                        ],
                    }
                )
            )
            extension = root / "garfield-extension"
            runner = BenchmarkRunner(
                base=root / "base",
                agents_repo=None,
                extension_repo=extension,
                runs_root=root / "runs",
                calibration=calibration,
                adapter_config=AdapterConfig(),
                seed=1,
            )

            self.assertEqual(runner._control_source("workflow-garfield"), extension.resolve())
            with self.assertRaisesRegex(RuntimeError, "--agents-repo is required"):
                runner._control_source("garfield")


if __name__ == "__main__":
    unittest.main()
