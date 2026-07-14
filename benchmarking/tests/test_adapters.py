from __future__ import annotations

import unittest
from pathlib import Path

from garfield_bench.adapters import GarfieldAdapter, SwampGarfieldAdapter, WorkflowGarfieldAdapter
from garfield_bench.adapters.base import AdapterConfig
from garfield_bench.adapters.workflow_garfield import _resource_attributes, _resource_key
from garfield_bench.cli import _parser
from garfield_bench.models import Case


class AdapterPromptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = AdapterConfig("codex", None, None, 1)
        self.case = Case(
            case_id="example",
            root=Path("."),
            prompt="Review the slice.",
            fixture_patch=Path("fixture.patch"),
            oracle={},
            hidden_tests=Path("hidden-tests"),
        )

    def test_garfield_prompt_names_installed_skill_path(self) -> None:
        prompt = GarfieldAdapter(self.config).prompts(self.case, "work-item")[0]
        self.assertIn(".agents/skills/garfield/SKILL.md", prompt)
        self.assertIn("Before any other action", prompt)

    def test_swamp_prompt_names_installed_skill_path_and_rejects_substitution(self) -> None:
        prompt = SwampGarfieldAdapter(self.config).prompts(self.case, "work-item")[0]
        self.assertIn(".agents/skills/swamp-garfield/SKILL.md", prompt)
        self.assertIn("Before any other action", prompt)
        self.assertIn("do not substitute the generic `swamp` skill", prompt)

    def test_cli_supports_treatment_only_verification_run(self) -> None:
        args = _parser().parse_args(
            [
                "run-one",
                "--base",
                "base",
                "--agents-repo",
                "agents",
                "--calibration",
                "calibration.json",
                "--case",
                "example",
                "--treatment",
                "swamp-garfield",
            ]
        )
        self.assertEqual(args.treatment, "swamp-garfield")

    def test_cli_supports_workflow_garfield(self) -> None:
        args = _parser().parse_args(
            [
                "run-one",
                "--base",
                "base",
                "--calibration",
                "calibration.json",
                "--case",
                "example",
                "--treatment",
                "workflow-garfield",
            ]
        )
        self.assertEqual(args.treatment, "workflow-garfield")
        self.assertIsNone(args.agents_repo)
        self.assertEqual(args.extension_repo, Path(__file__).resolve().parents[2])

    def test_workflow_garfield_has_no_coordinator_prompts(self) -> None:
        adapter = WorkflowGarfieldAdapter(AdapterConfig("codex", None, "high", 1))
        with self.assertRaises(NotImplementedError):
            adapter.prompts(self.case, "work-item")

    def test_resource_key_is_stable_and_safe(self) -> None:
        self.assertEqual(
            _resource_key("garfield-bench:run:abc"),
            _resource_key("garfield-bench:run:abc"),
        )
        self.assertRegex(_resource_key("garfield-bench:run:abc"), r"^[a-z0-9-]+$")

    def test_resource_attributes_accepts_data_get_envelope(self) -> None:
        attributes = {"workItem": "item", "status": "passed", "invocations": []}
        self.assertEqual(
            _resource_attributes({"data": {"attributes": attributes}}),
            attributes,
        )


if __name__ == "__main__":
    unittest.main()
