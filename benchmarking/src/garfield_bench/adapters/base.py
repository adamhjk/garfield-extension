from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from garfield_bench.app_server import run_app_server_session
from garfield_bench.models import AgentUsage, Case


@dataclass(frozen=True, slots=True)
class AdapterConfig:
    codex: str = "codex"
    model: str | None = None
    effort: str = "high"
    timeout_seconds: int = 1800


@dataclass(slots=True)
class AdapterResult:
    status: str
    session_ids: list[str]
    usage: list[AgentUsage]
    duration_ms: int
    blocker: str | None = None


class CoordinatorAdapter:
    treatment: str

    def __init__(self, config: AdapterConfig) -> None:
        self.config = config

    def run(
        self,
        case: Case,
        workspace: Path,
        run_dir: Path,
        run_id: str,
        work_item: str,
        control_repo: Path,
    ) -> AdapterResult:
        prompts = self.prompts(case, work_item)
        all_usage: list[AgentUsage] = []
        session_ids: list[str] = []
        started = time.monotonic()
        blocker: str | None = None
        status = "completed"

        for index, prompt in enumerate(prompts, start=1):
            session = self._run_session(
                prompt,
                workspace,
                control_repo,
                run_dir,
                run_id,
                index,
            )
            all_usage.extend(session["usage"])
            if session["thread_id"]:
                session_ids.append(session["thread_id"])
            if session["returncode"] != 0:
                status = "failed" if not session["timed_out"] else "timeout"
                blocker = session["error"]
                break

        return AdapterResult(
            status=status,
            session_ids=session_ids,
            usage=all_usage,
            duration_ms=int((time.monotonic() - started) * 1000),
            blocker=blocker,
        )

    def prompts(self, case: Case, work_item: str) -> list[str]:
        raise NotImplementedError

    def _run_session(
        self,
        prompt: str,
        workspace: Path,
        control_repo: Path,
        run_dir: Path,
        run_id: str,
        session_number: int,
    ) -> dict[str, object]:
        events_path = run_dir / f"coordinator-{session_number}.events.jsonl"
        final_path = run_dir / f"coordinator-{session_number}.final.txt"
        stderr_path = run_dir / f"coordinator-{session_number}.stderr.txt"
        environment = os.environ.copy()
        environment.update(
            {
                "SWAMP_REPO_DIR": str(control_repo),
                "GARFIELD_BENCH_RUN_ID": run_id,
                "GARFIELD_BENCH_TREATMENT": self.treatment,
            }
        )
        run = run_app_server_session(
            codex=self.config.codex,
            prompt=prompt,
            cwd=workspace,
            writable_roots=[workspace, control_repo],
            model=self.config.model,
            effort=self.config.effort,
            timeout_seconds=self.config.timeout_seconds,
            run_id=run_id,
            environment=environment,
            events_path=events_path,
            stderr_path=stderr_path,
        )
        final_path.write_text(run.final_message)
        error = run.error
        if run.returncode != 0 and error is None:
            error = f"coordinator app-server exited {run.returncode}: {run.stderr.strip()}"
        metadata = {
            "command": run.command + ["<turn-prompt-redacted-to-prompt-field>"],
            "prompt": prompt,
            "thread_id": run.root_thread,
            "returncode": run.returncode,
            "timed_out": run.timed_out,
            "duration_ms": run.duration_ms,
            "telemetry": "codex-app-server-exclusive-response-deltas",
        }
        (run_dir / f"coordinator-{session_number}.metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n"
        )
        return {
            "usage": run.collector.rows(),
            "thread_id": run.root_thread,
            "returncode": run.returncode,
            "timed_out": run.timed_out,
            "error": error,
        }
