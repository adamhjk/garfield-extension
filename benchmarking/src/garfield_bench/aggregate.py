from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


def aggregate_runs(runs_root: Path, factory_authoring_tokens: int | None = None) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for result_path in sorted(runs_root.glob("*/result.json")):
        run_dir = result_path.parent
        result = json.loads(result_path.read_text())
        grading_path = run_dir / "grading.json"
        grading = json.loads(grading_path.read_text()) if grading_path.exists() else {"passed": False}
        usage = [json.loads(line) for line in (run_dir / "usage.jsonl").read_text().splitlines() if line.strip()]
        coordinator = sum(int(row["total_tokens"]) for row in usage if row["parent_agent_id"] is None)
        delegated = sum(int(row["total_tokens"]) for row in usage if row["parent_agent_id"] is not None)
        input_tokens = sum(int(row.get("input_tokens", 0)) for row in usage)
        cached_input_tokens = sum(int(row.get("cached_input_tokens", 0)) for row in usage)
        output_tokens = sum(int(row.get("output_tokens", 0)) for row in usage)
        review_cycles = [int(row.get("cycle", 1)) for row in usage if row.get("stage") == "review"]
        records.append(
            {
                **result,
                "grade_passed": bool(grading.get("passed")),
                "total_agent_tree_tokens": coordinator + delegated,
                "coordinator_tokens": coordinator,
                "delegated_tokens": delegated,
                "input_tokens": input_tokens,
                "cached_input_tokens": cached_input_tokens,
                "uncached_input_tokens": input_tokens - cached_input_tokens,
                "output_tokens": output_tokens,
                "agent_count": len(usage),
                "review_cycles": max(review_cycles) if review_cycles else None,
                "cold_to_first_review_tokens": None,
                "resume_to_first_useful_action_tokens": None,
            }
        )

    grouped: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[(record["case_id"], record["treatment"])].append(record)

    groups: list[dict[str, Any]] = []
    for (case_id, treatment), values in sorted(grouped.items()):
        successes = [value for value in values if value["grade_passed"]]
        groups.append(
            {
                "case_id": case_id,
                "treatment": treatment,
                "runs": len(values),
                "successes": len(successes),
                "success_rate": len(successes) / len(values),
                "median_total_agent_tree_tokens": _median(values, "total_agent_tree_tokens"),
                "median_coordinator_tokens": _median(values, "coordinator_tokens"),
                "median_delegated_tokens": _median(values, "delegated_tokens"),
                "median_input_tokens": _median(values, "input_tokens"),
                "median_cached_input_tokens": _median(values, "cached_input_tokens"),
                "median_uncached_input_tokens": _median(values, "uncached_input_tokens"),
                "median_output_tokens": _median(values, "output_tokens"),
                "median_agent_count": _median(values, "agent_count"),
                "median_review_cycles": _median(values, "review_cycles"),
                "median_wall_clock_ms": _median(values, "duration_ms"),
                "median_cold_to_first_review_tokens": _median(values, "cold_to_first_review_tokens"),
                "median_resume_to_first_useful_action_tokens": _median(
                    values, "resume_to_first_useful_action_tokens"
                ),
                "median_tokens_per_success": _median(successes, "total_agent_tree_tokens") if successes else None,
                "token_dispersion": _dispersion(values, "total_agent_tree_tokens"),
            }
        )

    amortization = _amortization(groups, factory_authoring_tokens)
    return {
        "run_count": len(records),
        "records": records,
        "groups": groups,
        "factory_authoring_tokens": factory_authoring_tokens,
        "amortization": amortization,
        "limitations": [
            "cold-to-first-review and resume-to-first-useful-action token boundaries are null when the runtime does not emit token checkpoints at collaboration events",
            "qualitative patch comparison is intentionally separate from deterministic grading",
            "raw tree tokens equal input plus output; cached input is a subset of input, is not added twice, and is reported separately from uncached input",
        ],
    }


def _median(values: list[dict[str, Any]], field: str) -> float | None:
    items = [float(value[field]) for value in values if value.get(field) is not None]
    return statistics.median(items) if items else None


def _dispersion(values: list[dict[str, Any]], field: str) -> dict[str, float | None]:
    items = [float(value[field]) for value in values if value.get(field) is not None]
    if not items:
        return {"min": None, "max": None, "pstdev": None}
    return {
        "min": min(items),
        "max": max(items),
        "pstdev": statistics.pstdev(items) if len(items) > 1 else 0.0,
    }


def _amortization(groups: list[dict[str, Any]], authoring: int | None) -> list[dict[str, Any]]:
    garfield = [group["median_total_agent_tree_tokens"] for group in groups if group["treatment"] == "garfield"]
    swamp = [group["median_total_agent_tree_tokens"] for group in groups if group["treatment"] == "swamp-garfield"]
    if not garfield or not swamp:
        return []
    garfield_run = statistics.median(garfield)
    swamp_run = statistics.median(swamp)
    rows = []
    for count in (1, 5, 10, 25, 100):
        rows.append(
            {
                "work_items": count,
                "garfield_tokens": count * garfield_run,
                "swamp_garfield_tokens": None if authoring is None else authoring + count * swamp_run,
            }
        )
    return rows
