from __future__ import annotations

import json
import random
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Iterable

from .adapters import GarfieldAdapter, SwampGarfieldAdapter, WorkflowGarfieldAdapter
from .adapters.base import AdapterConfig, CoordinatorAdapter
from .grading import grade_workspace
from .models import Case, RunResult
from .telemetry import write_usage
from .workspace import (
    final_patch,
    install_coordinator_skill,
    materialize_control_repo,
    materialize_workspace,
)


class CalibrationRequired(RuntimeError):
    pass


class BenchmarkRunner:
    def __init__(
        self,
        *,
        base: Path,
        agents_repo: Path | None,
        extension_repo: Path,
        runs_root: Path,
        calibration: Path,
        adapter_config: AdapterConfig,
        seed: int,
    ) -> None:
        self.base = base.resolve()
        self.agents_repo = agents_repo.resolve() if agents_repo is not None else None
        self.extension_repo = extension_repo.resolve()
        self.runs_root = runs_root.resolve()
        self.adapter_config = adapter_config
        self.random = random.Random(seed)
        self.seed = seed
        self._require_calibration(calibration)

    @staticmethod
    def _require_calibration(path: Path) -> None:
        if not path.exists():
            raise CalibrationRequired(f"calibration file does not exist: {path}")
        payload = json.loads(path.read_text())
        if not payload.get("passed"):
            raise CalibrationRequired(f"telemetry calibration failed: {payload.get('reason', 'unknown reason')}")
        sessions = payload.get("sessions", [])
        roots = [row for row in sessions if row.get("parent_agent_id") is None]
        children = [row for row in sessions if row.get("parent_agent_id") is not None]
        if len(roots) != 1 or len(children) != 1:
            raise CalibrationRequired("calibration does not contain exactly one parent and one child session")

    def run_pair(self, case: Case, repetition: int) -> list[RunResult]:
        treatments = ["garfield", "swamp-garfield"]
        self.random.shuffle(treatments)
        return self._run_treatments(case, repetition, treatments, paired=True)

    def run_treatment(self, case: Case, repetition: int, treatment: str) -> RunResult:
        self._adapter(treatment)
        return self._run_treatments(case, repetition, [treatment], paired=False)[0]

    def _run_treatments(
        self,
        case: Case,
        repetition: int,
        treatments: list[str],
        *,
        paired: bool,
    ) -> list[RunResult]:
        self.runs_root.mkdir(parents=True, exist_ok=True)
        work_parent = self.runs_root / ".work"
        work_parent.mkdir(parents=True, exist_ok=True)
        work_root = Path(tempfile.mkdtemp(prefix=f"{case.case_id}-r{repetition:02d}-", dir=work_parent))
        prepared: dict[str, tuple[Path, Path, str]] = {}
        results: list[RunResult] = []
        try:
            for treatment in treatments:
                workspace = work_root / f"workspace-{treatment}"
                control = work_root / f"control-{treatment}"
                digest = materialize_workspace(self.base, case.fixture_patch, workspace)
                materialize_control_repo(self._control_source(treatment), self.base, control)
                prepared[treatment] = (workspace, control, digest)

            hashes = {prepared[treatment][2] for treatment in treatments}
            if len(hashes) != 1:
                raise RuntimeError(f"treatments received non-identical starting trees: {prepared}")

            for order, treatment in enumerate(treatments, start=1):
                workspace, control, digest = prepared[treatment]
                run_id = f"{case.case_id}-r{repetition:02d}-{treatment}"
                run_dir = self.runs_root / run_id
                if run_dir.exists():
                    raise RuntimeError(f"run directory already exists: {run_dir}")
                run_dir.mkdir(parents=True)
                work_item = f"garfield-bench:{run_id}:{uuid.uuid4()}"
                if treatment in {"garfield", "swamp-garfield"}:
                    install_coordinator_skill(workspace, self._require_agents_repo(treatment), treatment)
                adapter = self._adapter(treatment)
                started = time.monotonic()
                adapter_result = adapter.run(case, workspace, run_dir, run_id, work_item, control)
                patch = final_patch(workspace)
                (run_dir / "final.patch").write_text(patch)
                write_usage(run_dir / "usage.jsonl", adapter_result.usage)
                grade = grade_workspace(case, workspace, run_dir, patch)
                status = "passed" if adapter_result.status == "completed" and grade["passed"] else "failed"
                result = RunResult(
                    run_id=run_id,
                    case_id=case.case_id,
                    treatment=treatment,
                    status=status,
                    workspace_hash=digest,
                    work_item=work_item,
                    coordinator_sessions=adapter_result.session_ids,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    final_patch="final.patch",
                    blocker=adapter_result.blocker,
                )
                payload = result.to_dict()
                payload["randomized_order"] = order
                payload["random_seed"] = self.seed
                payload["paired"] = paired
                (run_dir / "result.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
                results.append(result)
        finally:
            shutil.rmtree(work_root, ignore_errors=True)
        return results

    def _adapter(self, treatment: str) -> CoordinatorAdapter:
        if treatment == "garfield":
            return GarfieldAdapter(self.adapter_config)
        if treatment == "swamp-garfield":
            return SwampGarfieldAdapter(self.adapter_config)
        if treatment == "workflow-garfield":
            return WorkflowGarfieldAdapter(self.adapter_config)
        raise ValueError(treatment)

    def _control_source(self, treatment: str) -> Path:
        if treatment == "workflow-garfield":
            return self.extension_repo
        return self._require_agents_repo(treatment)

    def _require_agents_repo(self, treatment: str) -> Path:
        if self.agents_repo is None:
            raise RuntimeError(f"--agents-repo is required for {treatment}")
        return self.agents_repo

    def run_schedule(self, cases: Iterable[Case], repetitions: int) -> list[RunResult]:
        schedule = [(case, repetition) for repetition in range(1, repetitions + 1) for case in cases]
        self.random.shuffle(schedule)
        results: list[RunResult] = []
        for case, repetition in schedule:
            results.extend(self.run_pair(case, repetition))
        return results
