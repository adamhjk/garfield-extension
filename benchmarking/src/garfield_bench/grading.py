from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .models import Case
from .workspace import changed_files


@dataclass(slots=True)
class CommandResult:
    command: list[str]
    exit_code: int
    duration_ms: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


def grade_workspace(case: Case, workspace: Path, run_dir: Path, final_patch: str) -> dict[str, Any]:
    public = [
        _run(["go", "test", "./..."], workspace, run_dir),
        _run(["go", "vet", "./..."], workspace, run_dir),
        _run(["go", "run", "./tools/generate", "-check"], workspace, run_dir),
    ]
    hidden = _run_hidden(case, workspace, run_dir)
    paths = changed_files(workspace)
    allowed_prefixes = [str(value) for value in case.oracle.get("allowed_path_prefixes", [])]
    unrelated = [path for path in paths if not any(path.startswith(prefix) for prefix in allowed_prefixes)]
    changed_lines = sum(
        1
        for line in final_patch.splitlines()
        if (line.startswith("+") or line.startswith("-"))
        and not line.startswith("+++")
        and not line.startswith("---")
    )
    evidence_paths = [
        *sorted(run_dir.glob("coordinator-*.events.jsonl")),
        *sorted(run_dir.glob("*.metadata.json")),
    ]
    event_text = "\n".join(path.read_text(errors="replace") for path in evidence_paths)
    validation_observed = "validate-slice" in event_text or "tools/validate.sh" in event_text

    assertions = [
        _assertion("public_validation", all(result.passed for result in public), _command_evidence(public)),
        _assertion("hidden_behavior", hidden.passed, _result_evidence(hidden)),
        _assertion(
            "generated_output_matches_source",
            public[2].passed,
            _result_evidence(public[2]),
        ),
        _assertion(
            "existing_behavior_unchanged",
            public[0].passed,
            "the complete visible Go test suite passed" if public[0].passed else _result_evidence(public[0]),
        ),
        _assertion(
            "no_unrelated_files",
            not unrelated,
            "all changed paths are in the case allowlist" if not unrelated else f"unrelated paths: {unrelated}",
        ),
        _assertion(
            "change_budget",
            len(paths) <= int(case.oracle["max_changed_files"])
            and changed_lines <= int(case.oracle["max_changed_lines"]),
            f"{len(paths)} files and {changed_lines} changed lines; limits are "
            f"{case.oracle['max_changed_files']} files and {case.oracle['max_changed_lines']} lines",
        ),
        _assertion(
            "coordinator_validation_observed",
            validation_observed,
            "coordinator event stream names the aggregate validation target"
            if validation_observed
            else "no validate-slice or tools/validate.sh invocation was present in coordinator events",
        ),
    ]
    grade = {
        "case_id": case.case_id,
        "passed": all(item["passed"] for item in assertions),
        "assertions": assertions,
        "seeded_defects_removed": hidden.passed and public[2].passed,
        "changed_files": paths,
        "unrelated_files": unrelated,
        "changed_lines": changed_lines,
        "public_commands": [asdict(result) for result in public],
        "hidden_command": asdict(hidden),
    }
    (run_dir / "grading.json").write_text(json.dumps(grade, indent=2, sort_keys=True) + "\n")
    return grade


def grade_fixture(case: Case, workspace: Path, run_dir: Path) -> dict[str, Any]:
    """Grade an unmodified prepared candidate without requiring coordinator evidence."""
    run_dir.mkdir(parents=True, exist_ok=True)
    public = [
        _run(["go", "test", "./..."], workspace, run_dir),
        _run(["go", "vet", "./..."], workspace, run_dir),
        _run(["go", "run", "./tools/generate", "-check"], workspace, run_dir),
    ]
    hidden = _run_hidden(case, workspace, run_dir)
    return {
        "public_passed": all(result.passed for result in public),
        "hidden_passed": hidden.passed,
        "public": [asdict(result) for result in public],
        "hidden": asdict(hidden),
    }


def _run_hidden(case: Case, workspace: Path, run_dir: Path) -> CommandResult:
    replace: dict[str, str] = {}
    for source in sorted(case.hidden_tests.rglob("*_test.go")):
        target = workspace / source.relative_to(case.hidden_tests)
        if target.exists():
            raise RuntimeError(f"hidden overlay target unexpectedly exists: {target}")
        replace[str(target.resolve())] = str(source.resolve())
    overlay = run_dir / "hidden-overlay.json"
    overlay.write_text(json.dumps({"Replace": replace}, indent=2, sort_keys=True) + "\n")
    return _run(["go", "test", f"-overlay={overlay.resolve()}", "./..."], workspace, run_dir)


def _run(command: list[str], workspace: Path, run_dir: Path) -> CommandResult:
    environment = os.environ.copy()
    cache = run_dir / "go-cache"
    cache.mkdir(parents=True, exist_ok=True)
    environment["GOCACHE"] = str(cache.resolve())
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        return CommandResult(
            command,
            completed.returncode,
            int((time.monotonic() - started) * 1000),
            completed.stdout,
            completed.stderr,
        )
    except subprocess.TimeoutExpired as error:
        return CommandResult(
            command,
            124,
            int((time.monotonic() - started) * 1000),
            str(error.stdout or ""),
            str(error.stderr or "") + "\ncommand timed out",
        )


def _assertion(text: str, passed: bool, evidence: str) -> dict[str, Any]:
    return {"text": text, "passed": passed, "evidence": evidence}


def _command_evidence(results: list[CommandResult]) -> str:
    return "; ".join(f"{' '.join(result.command)} => {result.exit_code}" for result in results)


def _result_evidence(result: CommandResult) -> str:
    output = (result.stdout + "\n" + result.stderr).strip()
    if len(output) > 1200:
        output = output[-1200:]
    return f"{' '.join(result.command)} => {result.exit_code}: {output}"
