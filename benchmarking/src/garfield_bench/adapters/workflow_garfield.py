from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from garfield_bench.models import AgentUsage, Case

from .base import AdapterResult, CoordinatorAdapter


class WorkflowGarfieldAdapter(CoordinatorAdapter):
    """Run the coordinator-free, single-method Swamp Garfield workflow."""

    treatment = "workflow-garfield"

    def prompts(self, case: Case, work_item: str) -> list[str]:
        raise NotImplementedError("workflow-garfield has no coordinator prompts")

    def run(
        self,
        case: Case,
        workspace: Path,
        run_dir: Path,
        run_id: str,
        work_item: str,
        control_repo: Path,
    ) -> AdapterResult:
        started = time.monotonic()
        inputs = {
            "runId": run_id,
            "workItem": work_item,
            "workspaceDir": str(workspace.resolve()),
            "intent": case.prompt,
            "validationProgram": "./tools/validate.sh",
            "validationArgs": [],
            "codexPath": self.config.codex,
            "model": self.config.model or "configured-default",
            "reasoningEffort": self.config.effort,
            "agentTimeoutMs": self.config.timeout_seconds * 1000,
            "maxActorCalls": 2,
        }
        input_path = run_dir / "workflow-garfield-input.json"
        input_path.write_text(json.dumps(inputs, indent=2, sort_keys=True) + "\n")
        environment = os.environ.copy()
        cache = run_dir / "go-cache"
        cache.mkdir(parents=True, exist_ok=True)
        environment.update(
            {
                "SWAMP_REPO_DIR": str(control_repo.resolve()),
                "GOCACHE": str(cache.resolve()),
                "GARFIELD_BENCH_RUN_ID": run_id,
                "GARFIELD_BENCH_TREATMENT": self.treatment,
            }
        )
        command = [
            "swamp",
            "workflow",
            "run",
            "@adam/garfield",
            "--input-file",
            str(input_path.resolve()),
            "--skip-reports",
            "--timeout",
            str(self.config.timeout_seconds * 3 + 60),
        ]
        timed_out = False
        try:
            completed = subprocess.run(
                command,
                cwd=control_repo,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
                timeout=self.config.timeout_seconds * 3 + 120,
            )
            returncode = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
        except subprocess.TimeoutExpired as error:
            timed_out = True
            returncode = 124
            stdout = str(error.stdout or "")
            stderr = str(error.stderr or "") + "\nworkflow-garfield timed out"

        (run_dir / "workflow-garfield.stdout.txt").write_text(stdout)
        (run_dir / "workflow-garfield.stderr.txt").write_text(stderr)
        metadata = {
            "command": command,
            "workflow": "@adam/garfield",
            "model_type": "@adam/garfield",
            "model_name": "workflow-garfield",
            "validation_target": "./tools/validate.sh",
            "returncode": returncode,
            "timed_out": timed_out,
            "coordinator": False,
        }
        (run_dir / "workflow-garfield.metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n"
        )

        payload: dict[str, Any] | None = None
        query_error: str | None = None
        data_name = f"result-{_resource_key(work_item)}"
        query = ["swamp", "data", "get", "workflow-garfield", data_name, "--json"]
        queried = subprocess.run(
            query,
            cwd=control_repo,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        (run_dir / "workflow-garfield.data.stdout.txt").write_text(queried.stdout)
        (run_dir / "workflow-garfield.data.stderr.txt").write_text(queried.stderr)
        if queried.returncode == 0:
            try:
                payload = _resource_attributes(json.loads(queried.stdout))
            except (json.JSONDecodeError, TypeError, ValueError) as error:
                query_error = f"could not parse result resource: {error}"
        else:
            query_error = f"result query exited {queried.returncode}: {queried.stderr.strip()}"

        usage: list[AgentUsage] = []
        session_ids: list[str] = []
        if payload is not None:
            (run_dir / "workflow-garfield.result.json").write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n"
            )
            for invocation in payload.get("invocations", []):
                if not isinstance(invocation, dict):
                    continue
                agent_id = str(invocation.get("agentId") or invocation.get("invocationId") or "")
                if not agent_id:
                    continue
                session_ids.append(agent_id)
                role = str(invocation.get("role") or "unknown")
                usage.append(
                    AgentUsage(
                        run_id=run_id,
                        agent_id=agent_id,
                        parent_agent_id=None,
                        role="reviewer" if role == "review" else "actor",
                        stage="review" if role == "review" else "fix",
                        cycle=int(invocation.get("cycle") or 1),
                        input_tokens=int(invocation.get("inputTokens") or 0),
                        cached_input_tokens=int(invocation.get("cachedInputTokens") or 0),
                        output_tokens=int(invocation.get("outputTokens") or 0),
                        reasoning_output_tokens=int(invocation.get("reasoningOutputTokens") or 0),
                        total_tokens=int(invocation.get("totalTokens") or 0),
                        duration_ms=int(invocation.get("durationMs") or 0),
                        tool_duration_ms=int(invocation.get("toolDurationMs") or 0),
                        tool_output_bytes=int(invocation.get("toolOutputBytes") or 0),
                        session_counting=str(
                            invocation.get("sessionCounting") or "codex-exec-turn-deltas"
                        ),
                    )
                )

        passed = returncode == 0 and payload is not None and payload.get("status") == "passed"
        blocker = None
        if not passed:
            blocker = query_error
            if payload is not None:
                blocker = str(payload.get("reason") or blocker or "workflow result blocked")
            if blocker is None:
                blocker = stderr.strip() or f"workflow exited {returncode}"
        return AdapterResult(
            status="completed" if passed else ("timeout" if timed_out else "failed"),
            session_ids=session_ids,
            usage=usage,
            duration_ms=int((time.monotonic() - started) * 1000),
            blocker=blocker,
        )


def _resource_key(work_item: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", work_item.lower()).strip("-")[:48] or "work-item"
    value = 2166136261
    for character in work_item:
        value ^= ord(character)
        value = (value * 16777619) & 0xFFFFFFFF
    return f"{slug}-{value:08x}"


def _resource_attributes(payload: Any) -> dict[str, Any]:
    """Accept the data-get envelopes used across supported Swamp versions."""

    if isinstance(payload, dict):
        if payload.get("workItem") and payload.get("status"):
            return payload
        for key in ("attributes", "content", "data", "resource"):
            value = payload.get(key)
            if isinstance(value, dict):
                try:
                    return _resource_attributes(value)
                except ValueError:
                    pass
        for value in payload.values():
            if isinstance(value, (dict, list)):
                try:
                    return _resource_attributes(value)
                except ValueError:
                    pass
    elif isinstance(payload, list):
        for value in payload:
            try:
                return _resource_attributes(value)
            except ValueError:
                pass
    raise ValueError("Swamp data response did not contain Garfield result attributes")
