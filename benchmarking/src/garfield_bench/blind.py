from __future__ import annotations

import json
import random
import re
import shutil
from collections import defaultdict
from pathlib import Path


def prepare_blind_review(runs_root: Path, output_root: Path, seed: int) -> dict[str, object]:
    randomizer = random.Random(seed)
    grouped: defaultdict[tuple[str, str], list[tuple[Path, dict[str, object]]]] = defaultdict(list)
    for result_path in sorted(runs_root.glob("*/result.json")):
        payload = json.loads(result_path.read_text())
        run_id = str(payload["run_id"])
        match = re.search(r"-r(\d+)-(?:garfield|swamp-garfield)$", run_id)
        repetition = match.group(1) if match else run_id
        grouped[(str(payload["case_id"]), repetition)].append((result_path.parent, payload))

    output_root.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, object] = {"seed": seed, "comparisons": []}
    prepared = 0
    for (case_id, repetition), values in sorted(grouped.items()):
        by_treatment = {str(payload["treatment"]): (run_dir, payload) for run_dir, payload in values}
        if set(by_treatment) != {"garfield", "swamp-garfield"}:
            continue
        order = ["garfield", "swamp-garfield"]
        randomizer.shuffle(order)
        comparison_id = f"{case_id}-r{repetition}"
        destination = output_root / comparison_id
        destination.mkdir()
        labels: dict[str, str] = {}
        for label, treatment in zip(("A", "B"), order, strict=True):
            source = by_treatment[treatment][0] / "final.patch"
            shutil.copy2(source, destination / f"{label}.patch")
            labels[label] = treatment
        (destination / "review.md").write_text(
            "# Blind patch comparison\n\n"
            f"Case: `{case_id}`\n\n"
            "Compare `A.patch` and `B.patch` without trying to identify the coordinator. "
            "Judge intent preservation, correctness, minimality, test quality, and unrelated changes.\n\n"
            "Winner: A / B / tie\n\nRationale:\n"
        )
        mapping["comparisons"].append({"id": comparison_id, "labels": labels})
        prepared += 1
    (output_root / "mapping.private.json").write_text(json.dumps(mapping, indent=2, sort_keys=True) + "\n")
    (output_root / "README.md").write_text(
        "# Blind review bundle\n\n"
        "Give reviewers only the comparison directories. Keep `mapping.private.json` hidden "
        "until all qualitative judgments are final. Qualitative results must remain separate "
        "from deterministic grading.\n"
    )
    return {"prepared": prepared, "output": str(output_root), "mapping": str(output_root / "mapping.private.json")}
