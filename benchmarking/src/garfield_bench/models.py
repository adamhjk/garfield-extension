from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class AgentUsage:
    run_id: str
    agent_id: str
    parent_agent_id: str | None
    role: str
    stage: str
    cycle: int
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    total_tokens: int = 0
    duration_ms: int = 0
    tool_duration_ms: int = 0
    tool_output_bytes: int = 0
    session_counting: str = "per-turn-deltas"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CalibrationResult:
    passed: bool
    reason: str
    sessions: list[AgentUsage] = field(default_factory=list)
    computed_tree_total: int | None = None
    runtime_tree_total: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "sessions": [session.to_dict() for session in self.sessions],
            "computed_tree_total": self.computed_tree_total,
            "runtime_tree_total": self.runtime_tree_total,
        }


@dataclass(frozen=True, slots=True)
class Case:
    case_id: str
    root: Path
    prompt: str
    fixture_patch: Path
    oracle: dict[str, Any]
    hidden_tests: Path

    @property
    def forced_restart(self) -> bool:
        return bool(self.oracle.get("forced_restart_after_material_fix", False))

    @classmethod
    def load(cls, root: Path) -> "Case":
        import json

        oracle = json.loads((root / "oracle.json").read_text())
        return cls(
            case_id=str(oracle["case_id"]),
            root=root,
            prompt=(root / "prompt.md").read_text().strip(),
            fixture_patch=root / "fixture.patch",
            oracle=oracle,
            hidden_tests=root / "hidden-tests",
        )


@dataclass(slots=True)
class RunResult:
    run_id: str
    case_id: str
    treatment: str
    status: str
    workspace_hash: str
    work_item: str
    coordinator_sessions: list[str]
    duration_ms: int
    final_patch: str
    blocker: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
