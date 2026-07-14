from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from garfield_bench.workspace import materialize_control_repo, tree_hash


class WorkspaceTests(unittest.TestCase):
    def test_treatment_skill_is_excluded_from_system_tree_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.go").write_text("package main\n")
            first = tree_hash(root)
            skill = root / ".agents" / "skills" / "garfield"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("treatment")
            self.assertEqual(first, tree_hash(root))

    def test_normal_file_changes_tree_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "main.go"
            path.write_text("package main\n")
            first = tree_hash(root)
            path.write_text("package changed\n")
            self.assertNotEqual(first, tree_hash(root))

    def test_control_repo_merges_treatment_and_target_workflows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            treatment = root / "extension"
            ledgerlite = root / "ledgerlite"
            destination = root / "control"
            (treatment / "workflows").mkdir(parents=True)
            (ledgerlite / "workflows").mkdir(parents=True)
            (treatment / "workflows" / "garfield.yaml").write_text("name: garfield\n")
            (ledgerlite / "workflows" / "validate.yaml").write_text("name: validate\n")

            materialize_control_repo(treatment, ledgerlite, destination)

            self.assertTrue((destination / "workflows" / "garfield.yaml").exists())
            self.assertTrue((destination / "workflows" / "validate.yaml").exists())


if __name__ == "__main__":
    unittest.main()
