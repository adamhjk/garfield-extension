from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .models import AgentUsage, CalibrationResult


class TelemetryError(RuntimeError):
    pass


@dataclass(slots=True)
class _Session:
    agent_id: str
    parent_agent_id: str | None = None
    role: str = "coordinator"
    stage: str = "coordinator"
    cycle: int = 1
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    duration_ms: int = 0
    tool_duration_ms: int = 0
    tool_output_bytes: int = 0
    counting_mode: str | None = None


class CodexJSONLCollector:
    """Collect exclusive per-session deltas from Codex JSONL.

    The collector deliberately does not infer child usage from root totals or
    tool output sizes. A runtime must emit a child thread plus that thread's own
    usage event (or an explicit ``agent.usage`` record) for it to count.
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.sessions: dict[str, _Session] = {}
        self.current_thread: str | None = None
        self.root_thread: str | None = None
        self._completed_turns: set[tuple[str, str]] = set()
        self._turn_sequence: defaultdict[str, int] = defaultdict(int)
        self.runtime_tree_total: int | None = None

    def consume_lines(self, lines: Iterable[str]) -> None:
        for line in lines:
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                self.consume(event)

    def consume(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type", ""))
        if event_type == "thread.started":
            thread_id = str(event.get("thread_id") or event.get("threadId") or "")
            if not thread_id:
                return
            parent = event.get("parent_thread_id") or event.get("parentThreadId")
            role = str(event.get("role") or ("delegated" if parent else "coordinator"))
            self.sessions.setdefault(thread_id, _Session(thread_id, str(parent) if parent else None, role, role))
            self.current_thread = thread_id
            if parent is None and self.root_thread is None:
                self.root_thread = thread_id
            return

        if event_type in {"agent.usage", "subagent.usage"}:
            self._consume_explicit_usage(event)
            return

        if event_type == "turn.completed":
            thread_id = str(
                event.get("thread_id")
                or event.get("threadId")
                or self.root_thread
                or self.current_thread
                or ""
            )
            if not thread_id:
                raise TelemetryError("turn.completed did not identify a thread")
            session = self.sessions.setdefault(thread_id, _Session(thread_id))
            self._turn_sequence[thread_id] += 1
            turn_key = str(event.get("turn_id") or event.get("turnId") or self._turn_sequence[thread_id])
            key = (thread_id, turn_key)
            if key in self._completed_turns:
                return
            if session.counting_mode not in {None, "per-turn-deltas"}:
                raise TelemetryError(f"session {thread_id} mixed final totals with per-turn deltas")
            session.counting_mode = "per-turn-deltas"
            self._completed_turns.add(key)
            self._add_usage(session, event.get("usage", {}))
            duration = event.get("duration_ms") or event.get("durationMs") or 0
            session.duration_ms += int(duration)
            tree_usage = event.get("tree_usage") or event.get("treeUsage")
            if isinstance(tree_usage, dict):
                self.runtime_tree_total = _total_from_usage(tree_usage)
            return

        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "collab_tool_call":
            sender = str(item.get("sender_thread_id") or item.get("senderThreadId") or self.current_thread or "")
            for receiver in item.get("receiver_thread_ids", item.get("receiverThreadIds", [])) or []:
                receiver_id = str(receiver)
                self.sessions.setdefault(receiver_id, _Session(receiver_id, sender or None, "delegated", "review"))

        if event_type in {"exec_command_end", "mcp_tool_call_end"}:
            thread_id = str(event.get("thread_id") or event.get("threadId") or self.current_thread or "")
            if thread_id:
                session = self.sessions.setdefault(thread_id, _Session(thread_id))
                session.tool_duration_ms += int(event.get("duration_ms") or event.get("durationMs") or 0)
                output = event.get("output", "")
                session.tool_output_bytes += len(str(output).encode())

    def _consume_explicit_usage(self, event: dict[str, Any]) -> None:
        agent_id = str(event.get("agent_id") or event.get("agentId") or event.get("thread_id") or "")
        if not agent_id:
            raise TelemetryError("explicit agent usage did not identify an agent")
        parent = event.get("parent_agent_id") or event.get("parentAgentId") or event.get("parent_thread_id")
        session = self.sessions.setdefault(
            agent_id,
            _Session(
                agent_id,
                str(parent) if parent else None,
                str(event.get("role") or ("delegated" if parent else "coordinator")),
                str(event.get("stage") or "unknown"),
                int(event.get("cycle") or 1),
            ),
        )
        event_key = str(event.get("usage_id") or event.get("usageId") or event.get("turn_id") or len(self._completed_turns) + 1)
        key = (agent_id, event_key)
        if key in self._completed_turns:
            return
        if session.counting_mode not in {None, "explicit-session-deltas"}:
            raise TelemetryError(f"session {agent_id} mixed per-turn deltas with final totals")
        session.counting_mode = "explicit-session-deltas"
        self._completed_turns.add(key)
        self._add_usage(session, event.get("usage", event))
        session.duration_ms += int(event.get("duration_ms") or event.get("durationMs") or 0)

    @staticmethod
    def _add_usage(session: _Session, usage: Any) -> None:
        if not isinstance(usage, dict):
            return
        session.input_tokens += int(usage.get("input_tokens") or usage.get("inputTokens") or 0)
        session.cached_input_tokens += int(usage.get("cached_input_tokens") or usage.get("cachedInputTokens") or 0)
        session.output_tokens += int(usage.get("output_tokens") or usage.get("outputTokens") or 0)
        session.reasoning_output_tokens += int(
            usage.get("reasoning_output_tokens") or usage.get("reasoningOutputTokens") or 0
        )

    def rows(self) -> list[AgentUsage]:
        rows: list[AgentUsage] = []
        for session in self.sessions.values():
            if session.input_tokens == 0 and session.output_tokens == 0:
                continue
            rows.append(
                AgentUsage(
                    run_id=self.run_id,
                    agent_id=session.agent_id,
                    parent_agent_id=session.parent_agent_id,
                    role=session.role,
                    stage=session.stage,
                    cycle=session.cycle,
                    input_tokens=session.input_tokens,
                    cached_input_tokens=session.cached_input_tokens,
                    output_tokens=session.output_tokens,
                    reasoning_output_tokens=session.reasoning_output_tokens,
                    total_tokens=session.input_tokens + session.output_tokens,
                    duration_ms=session.duration_ms,
                    tool_duration_ms=session.tool_duration_ms,
                    tool_output_bytes=session.tool_output_bytes,
                    session_counting=session.counting_mode or "unknown",
                )
            )
        return sorted(rows, key=lambda row: (row.parent_agent_id is not None, row.agent_id))


_USAGE_KEYS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


class CodexAppServerCollector:
    """Collect exclusive usage for an app-server agent thread tree.

    App-server emits ``thread/tokenUsage/updated`` for every root and subagent
    thread on the same connection. Each update contains a per-response ``last``
    delta and a per-thread cumulative ``total``. Rows are built only from the
    deltas; the cumulative totals are retained as an independent runtime ledger
    and must reconcile exactly.
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.sessions: dict[str, _Session] = {}
        self.root_thread: str | None = None
        self.final_messages: dict[str, str] = {}
        self.active_threads: set[str] = set()
        self.completed_threads: set[str] = set()
        self._runtime_totals: dict[str, dict[str, int]] = {}
        self._usage_updates: set[tuple[str, str, tuple[int, ...]]] = set()
        self._completed_turns: set[tuple[str, str]] = set()
        self._completed_tools: set[tuple[str, str]] = set()

    def consume_lines(self, lines: Iterable[str]) -> None:
        for line in lines:
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                self.consume(event)

    def register_thread(
        self,
        thread_id: str,
        parent_thread_id: str | None = None,
        *,
        agent_path: str | None = None,
        root: bool = False,
    ) -> None:
        if not thread_id:
            raise TelemetryError("app-server thread record did not identify a thread")
        session = self.sessions.setdefault(thread_id, _Session(thread_id))
        if parent_thread_id:
            if session.parent_agent_id not in {None, parent_thread_id}:
                raise TelemetryError(
                    f"thread {thread_id} has conflicting parents "
                    f"{session.parent_agent_id} and {parent_thread_id}"
                )
            session.parent_agent_id = parent_thread_id
            session.role = _role_from_agent_path(agent_path)
            session.stage = _stage_from_agent_path(agent_path)
        if root or (parent_thread_id is None and self.root_thread is None):
            if self.root_thread not in {None, thread_id}:
                raise TelemetryError(f"app-server stream contains multiple roots: {self.root_thread}, {thread_id}")
            self.root_thread = thread_id

    def consume(self, event: dict[str, Any]) -> None:
        method = str(event.get("method") or "")
        params = event.get("params")
        if not isinstance(params, dict):
            return

        if method == "thread/started":
            thread = params.get("thread")
            if isinstance(thread, dict):
                parent = thread.get("parentThreadId") or thread.get("parent_thread_id")
                self.register_thread(
                    str(thread.get("id") or ""),
                    str(parent) if parent else None,
                    agent_path=str(thread.get("agentRole") or "") or None,
                )
            return

        if method == "thread/tokenUsage/updated":
            self._consume_usage(params)
            return

        thread_id = str(params.get("threadId") or params.get("thread_id") or "")
        if method == "turn/started" and thread_id:
            self.sessions.setdefault(thread_id, _Session(thread_id))
            self.active_threads.add(thread_id)
            return

        if method == "turn/completed" and thread_id:
            turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
            turn_id = str(turn.get("id") or "")
            key = (thread_id, turn_id)
            if key not in self._completed_turns:
                self._completed_turns.add(key)
                session = self.sessions.setdefault(thread_id, _Session(thread_id))
                session.duration_ms += int(turn.get("durationMs") or turn.get("duration_ms") or 0)
            self.active_threads.discard(thread_id)
            self.completed_threads.add(thread_id)
            return

        if method not in {"item/started", "item/completed"} or not thread_id:
            return
        item = params.get("item")
        if not isinstance(item, dict):
            return
        item_type = str(item.get("type") or "")

        if item_type in {"subAgentActivity", "sub_agent_activity"} and str(item.get("kind")) == "started":
            child = str(item.get("agentThreadId") or item.get("agent_thread_id") or "")
            self.register_thread(
                child,
                thread_id,
                agent_path=str(item.get("agentPath") or item.get("agent_path") or "") or None,
            )
            return

        if item_type in {"collabAgentToolCall", "collab_tool_call"}:
            sender = str(item.get("senderThreadId") or item.get("sender_thread_id") or thread_id)
            receivers = item.get("receiverThreadIds") or item.get("receiver_thread_ids") or []
            for receiver in receivers:
                self.register_thread(str(receiver), sender)
            return

        if method != "item/completed":
            return
        if item_type in {"agentMessage", "agent_message"}:
            text = item.get("text")
            if isinstance(text, str) and text:
                self.final_messages[thread_id] = text
            return
        if item_type not in {"commandExecution", "command_execution", "mcpToolCall", "mcp_tool_call"}:
            return
        item_id = str(item.get("id") or "")
        key = (thread_id, item_id)
        if key in self._completed_tools:
            return
        self._completed_tools.add(key)
        session = self.sessions.setdefault(thread_id, _Session(thread_id))
        session.tool_duration_ms += int(item.get("durationMs") or item.get("duration_ms") or 0)
        output = item.get("aggregatedOutput") or item.get("output") or ""
        session.tool_output_bytes += len(str(output).encode())

    def _consume_usage(self, params: dict[str, Any]) -> None:
        thread_id = str(params.get("threadId") or params.get("thread_id") or "")
        turn_id = str(params.get("turnId") or params.get("turn_id") or "")
        token_usage = params.get("tokenUsage") or params.get("token_usage")
        if not thread_id or not isinstance(token_usage, dict):
            raise TelemetryError("app-server token usage did not identify a thread")
        total = _usage_breakdown(token_usage.get("total"))
        last = _usage_breakdown(token_usage.get("last"))
        fingerprint = tuple(total[key] for key in _USAGE_KEYS)
        update_key = (thread_id, turn_id, fingerprint)
        if update_key in self._usage_updates:
            return
        self._usage_updates.add(update_key)

        previous = self._runtime_totals.get(thread_id, {key: 0 for key in _USAGE_KEYS})
        delta = {key: total[key] - previous[key] for key in _USAGE_KEYS}
        if any(value < 0 for value in delta.values()):
            raise TelemetryError(f"thread {thread_id} cumulative token usage decreased")
        if delta != last:
            raise TelemetryError(
                f"thread {thread_id} response delta does not reconcile with its cumulative total: "
                f"computed {delta}, runtime {last}"
            )
        self._runtime_totals[thread_id] = total
        session = self.sessions.setdefault(thread_id, _Session(thread_id))
        if session.counting_mode not in {None, "app-server-response-deltas"}:
            raise TelemetryError(f"session {thread_id} mixed incompatible counting modes")
        session.counting_mode = "app-server-response-deltas"
        session.input_tokens += last["input_tokens"]
        session.cached_input_tokens += last["cached_input_tokens"]
        session.output_tokens += last["output_tokens"]
        session.reasoning_output_tokens += last["reasoning_output_tokens"]

    @property
    def runtime_tree_total(self) -> int | None:
        if not self._runtime_totals:
            return None
        return sum(total["total_tokens"] for total in self._runtime_totals.values())

    def validate_complete_tree(self) -> None:
        if self.root_thread is None:
            raise TelemetryError("app-server stream omitted the root thread")
        missing_usage = sorted(
            thread_id for thread_id, session in self.sessions.items() if session.counting_mode is None
        )
        if missing_usage:
            raise TelemetryError(f"agent sessions omitted token usage: {', '.join(missing_usage)}")
        orphans = sorted(
            thread_id
            for thread_id, session in self.sessions.items()
            if thread_id != self.root_thread and session.parent_agent_id is None
        )
        if orphans:
            raise TelemetryError(f"agent sessions omitted parent links: {', '.join(orphans)}")
        for thread_id, session in self.sessions.items():
            parent = session.parent_agent_id
            if parent is not None and parent not in self.sessions:
                raise TelemetryError(f"thread {thread_id} references missing parent {parent}")
            seen = {thread_id}
            while parent is not None:
                if parent in seen:
                    raise TelemetryError(f"agent parent links contain a cycle at {parent}")
                seen.add(parent)
                parent_session = self.sessions.get(parent)
                parent = parent_session.parent_agent_id if parent_session else None
        ledger = self.runtime_tree_total
        computed = sum(row.total_tokens for row in self.rows())
        if ledger is None or computed != ledger:
            raise TelemetryError(f"exclusive tree total {computed} does not match runtime ledger {ledger}")

    def rows(self) -> list[AgentUsage]:
        rows: list[AgentUsage] = []
        for session in self.sessions.values():
            rows.append(
                AgentUsage(
                    run_id=self.run_id,
                    agent_id=session.agent_id,
                    parent_agent_id=session.parent_agent_id,
                    role=session.role,
                    stage=session.stage,
                    cycle=session.cycle,
                    input_tokens=session.input_tokens,
                    cached_input_tokens=session.cached_input_tokens,
                    output_tokens=session.output_tokens,
                    reasoning_output_tokens=session.reasoning_output_tokens,
                    total_tokens=session.input_tokens + session.output_tokens,
                    duration_ms=session.duration_ms,
                    tool_duration_ms=session.tool_duration_ms,
                    tool_output_bytes=session.tool_output_bytes,
                    session_counting=session.counting_mode or "unknown",
                )
            )
        return sorted(rows, key=lambda row: (row.parent_agent_id is not None, row.agent_id))


def calibrate_events(
    lines: Iterable[str], *, runtime_tree_total: int | None = None, run_id: str = "calibration"
) -> CalibrationResult:
    buffered = list(lines)
    collector: CodexJSONLCollector | CodexAppServerCollector
    collector = CodexAppServerCollector(run_id) if _is_app_server_stream(buffered) else CodexJSONLCollector(run_id)
    try:
        collector.consume_lines(buffered)
        if isinstance(collector, CodexAppServerCollector):
            collector.validate_complete_tree()
    except TelemetryError as error:
        return CalibrationResult(False, f"telemetry stream is ambiguous: {error}", collector.rows())
    sessions = collector.rows()
    roots = [row for row in sessions if row.parent_agent_id is None]
    children = [row for row in sessions if row.parent_agent_id is not None]
    computed = sum(row.total_tokens for row in sessions) if sessions else None
    ledger = runtime_tree_total if runtime_tree_total is not None else collector.runtime_tree_total

    if len(roots) != 1 or len(children) != 1:
        return CalibrationResult(
            False,
            f"expected one parent and one child usage session; observed {len(roots)} parent and {len(children)} child",
            sessions,
            computed,
            ledger,
        )
    if children[0].parent_agent_id != roots[0].agent_id:
        return CalibrationResult(False, "child parent id does not match the root session", sessions, computed, ledger)
    if ledger is None:
        return CalibrationResult(
            False,
            "no independent runtime/provider tree total was supplied for reconciliation",
            sessions,
            computed,
            None,
        )
    if computed != ledger:
        return CalibrationResult(
            False,
            f"exclusive session total {computed} does not match runtime ledger {ledger}",
            sessions,
            computed,
            ledger,
        )
    return CalibrationResult(True, "exclusive parent/child totals reconcile exactly", sessions, computed, ledger)


def run_live_calibration(codex: str = "codex", model: str | None = None) -> tuple[CalibrationResult, str]:
    from .app_server import run_app_server_session

    prompt = (
        "Telemetry protocol calibration. Spawn exactly one subagent to inspect "
        f"{Path(__file__).resolve()} and identify one concrete nested-accounting risk. "
        "Do not inspect the file yourself. Wait for that subagent, then return only its one-sentence finding."
    )
    run = run_app_server_session(
        codex=codex,
        prompt=prompt,
        cwd=Path.cwd(),
        writable_roots=[Path.cwd()],
        model=model,
        effort="high",
        timeout_seconds=180,
        run_id="calibration",
    )
    stream = run.stream
    result = calibrate_events(stream.splitlines())
    if run.returncode != 0:
        result.passed = False
        result.reason = f"codex app-server calibration exited {run.returncode}: {run.error or run.stderr.strip()}"
    elif not result.passed:
        result.reason = f"{result.reason}; live call duration {run.duration_ms}ms"
    return result, stream


def write_usage(path: Path, rows: Iterable[AgentUsage]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row.to_dict(), sort_keys=True) + "\n")


def _total_from_usage(usage: dict[str, Any]) -> int:
    explicit = usage.get("total_tokens") or usage.get("totalTokens")
    if explicit is not None:
        return int(explicit)
    return int(usage.get("input_tokens") or usage.get("inputTokens") or 0) + int(
        usage.get("output_tokens") or usage.get("outputTokens") or 0
    )


def _usage_breakdown(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        raise TelemetryError("app-server token usage omitted a total or last breakdown")
    result = {
        "input_tokens": int(value.get("inputTokens") or value.get("input_tokens") or 0),
        "cached_input_tokens": int(value.get("cachedInputTokens") or value.get("cached_input_tokens") or 0),
        "output_tokens": int(value.get("outputTokens") or value.get("output_tokens") or 0),
        "reasoning_output_tokens": int(
            value.get("reasoningOutputTokens") or value.get("reasoning_output_tokens") or 0
        ),
        "total_tokens": int(value.get("totalTokens") or value.get("total_tokens") or 0),
    }
    if result["total_tokens"] != result["input_tokens"] + result["output_tokens"]:
        raise TelemetryError(f"runtime token breakdown is internally inconsistent: {result}")
    return result


def _is_app_server_stream(lines: Iterable[str]) -> bool:
    for line in lines:
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(event, dict) and str(event.get("method", "")).startswith("thread/"):
            return True
    return False


def _role_from_agent_path(agent_path: str | None) -> str:
    if not agent_path:
        return "delegated"
    role = agent_path.rstrip("/").rsplit("/", 1)[-1]
    return role or "delegated"


def _stage_from_agent_path(agent_path: str | None) -> str:
    role = _role_from_agent_path(agent_path).lower()
    if "review" in role or "inspect" in role or "audit" in role:
        return "review"
    if "verify" in role or "test" in role or "validation" in role:
        return "verification"
    if "fix" in role or "implement" in role or "worker" in role:
        return "fix"
    return "delegated"
