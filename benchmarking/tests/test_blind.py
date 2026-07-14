from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from garfield_bench.blind import prepare_blind_review


class BlindReviewTests(unittest.TestCase):
    def test_pair_is_anonymized_and_mapping_is_separate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root / "runs"
            for treatment in ("garfield", "swamp-garfield"):
                run_id = f"contained-dry-run-r01-{treatment}"
                run = runs / run_id
                run.mkdir(parents=True)
                (run / "result.json").write_text(
                    json.dumps(
                        {
                            "run_id": run_id,
                            "case_id": "contained-dry-run",
                            "treatment": treatment,
                        }
                    )
                )
                (run / "final.patch").write_text(f"{treatment}\n")
            result = prepare_blind_review(runs, root / "blind", seed=7)
            self.assertEqual(result["prepared"], 1)
            comparison = root / "blind" / "contained-dry-run-r01"
            self.assertTrue((comparison / "A.patch").exists())
            self.assertNotIn("garfield", (comparison / "review.md").read_text().lower())


if __name__ == "__main__":
    unittest.main()
