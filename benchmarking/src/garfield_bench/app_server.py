from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, TextIO

from .telemetry import CodexAppServerCollector, TelemetryError


@dataclass(slots=True)
class AppServerRun:
    collector: CodexAppServerCollector
    stream: str
    stderr: str
    final_message: str
    root_thread: str | None
    returncode: int
    timed_out: bool
    duration_ms: int
    error: str | None
    command: list[str]


def run_app_server_session(
    *,
    codex: str,
    prompt: str,
    cwd: Path,
    writable_roots: list[Path],
    model: str | None,
    effort: str,
    timeout_seconds: int,
    run_id: str,
    environment: Mapping[str, str] | None = None,
    events_path: Path | None = None,
    stderr_path: Path | None = None,
) -> AppServerRun:
    """Run one fresh ephemeral turn and retain the complete agent-tree stream."""

    command = [
        codex,
        "app-server",
        "--stdio",
        "--enable",
        "multi_agent",
        "-c",
        "agents.max_threads=4",
        "-c",
        "agents.max_depth=2",
    ]
    process_environment = os.environ.copy()
    if environment:
        process_environment.update(environment)
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=process_environment,
        text=True,
        bufsize=1,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.stdin is None or process.stdout is None or process.stderr is None:
        process.kill()
        raise RuntimeError("failed to open codex app-server pipes")

    stdout_queue: queue.Queue[str | None] = queue.Queue()
    stderr_chunks: list[str] = []
    stdout_reader = threading.Thread(target=_read_lines, args=(process.stdout, stdout_queue), daemon=True)
    stderr_reader = threading.Thread(target=_read_stderr, args=(process.stderr, stderr_chunks), daemon=True)
    stdout_reader.start()
    stderr_reader.start()

    collector = CodexAppServerCollector(run_id)
    stream_lines: list[str] = []
    root_thread: str | None = None
    root_completed = False
    timed_out = False
    error: str | None = None

    def send(message: dict[str, object]) -> None:
        assert process.stdin is not None
        process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        process.stdin.flush()

    initialize_id = 1
    thread_start_id = 2
    turn_start_id = 3
    send(
        {
            "id": initialize_id,
            "method": "initialize",
            "params": {
                "clientInfo": {
                    "name": "garfield_bench",
                    "title": "Garfield benchmark",
                    "version": "0.1.0",
                },
                "capabilities": {
                    "experimentalApi": True,
                    "optOutNotificationMethods": [
                        "item/agentMessage/delta",
                        "item/plan/delta",
                        "item/reasoning/summaryTextDelta",
                        "item/reasoning/textDelta",
                        "item/commandExecution/outputDelta",
                    ],
                },
            },
        }
    )

    deadline = started + timeout_seconds
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                error = f"app-server session exceeded {timeout_seconds}s"
                break
            try:
                line = stdout_queue.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                if process.poll() is not None:
                    error = f"app-server exited before the root turn completed ({process.returncode})"
                    break
                continue
            if line is None:
                if not root_completed:
                    error = f"app-server stream ended before the root turn completed ({process.poll()})"
                break
            stream_lines.append(line)
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            collector.consume(message)

            if message.get("id") == initialize_id:
                if "error" in message:
                    error = f"initialize failed: {message['error']}"
                    break
                send({"method": "initialized", "params": {}})
                thread_params: dict[str, object] = {
                    "cwd": str(cwd.resolve()),
                    "runtimeWorkspaceRoots": [str(path.resolve()) for path in writable_roots],
                    "approvalPolicy": "never",
                    "sandbox": "workspace-write",
                    "ephemeral": True,
                    "config": {
                        "features": {"multi_agent": True},
                        "agents": {"max_threads": 4, "max_depth": 2},
                    },
                }
                if model:
                    thread_params["model"] = model
                send({"id": thread_start_id, "method": "thread/start", "params": thread_params})
                continue

            if message.get("id") == thread_start_id:
                if "error" in message:
                    error = f"thread/start failed: {message['error']}"
                    break
                result = message.get("result")
                thread = result.get("thread") if isinstance(result, dict) else None
                if not isinstance(thread, dict) or not thread.get("id"):
                    error = "thread/start response omitted the root thread id"
                    break
                root_thread = str(thread["id"])
                collector.register_thread(root_thread, root=True)
                send(
                    {
                        "id": turn_start_id,
                        "method": "turn/start",
                        "params": {
                            "threadId": root_thread,
                            "input": [{"type": "text", "text": prompt}],
                            "effort": effort,
                        },
                    }
                )
                continue

            if message.get("id") == turn_start_id and "error" in message:
                error = f"turn/start failed: {message['error']}"
                break

            method = str(message.get("method") or "")
            if "id" in message and method:
                error = f"unsupported app-server request during non-interactive run: {method}"
                break
            if method == "turn/completed":
                params = message.get("params")
                thread_id = str(params.get("threadId") or "") if isinstance(params, dict) else ""
                if thread_id == root_thread:
                    root_completed = True
                    if not collector.active_threads:
                        break
    except (BrokenPipeError, OSError, TelemetryError) as caught:
        error = str(caught)
    finally:
        if process.stdin and not process.stdin.closed:
            process.stdin.close()
        try:
            process.wait(timeout=10 if not timed_out else 2)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        stdout_reader.join(timeout=1)
        stderr_reader.join(timeout=1)

    if error is None:
        try:
            collector.validate_complete_tree()
        except TelemetryError as caught:
            error = str(caught)

    stream = "".join(stream_lines)
    stderr = "".join(stderr_chunks)
    if events_path:
        events_path.parent.mkdir(parents=True, exist_ok=True)
        events_path.write_text(stream)
    if stderr_path:
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.write_text(stderr)
    final_message = collector.final_messages.get(root_thread or "", "")
    returncode = 0 if root_completed and not error and process.returncode == 0 else (process.returncode or 78)
    return AppServerRun(
        collector=collector,
        stream=stream,
        stderr=stderr,
        final_message=final_message,
        root_thread=root_thread,
        returncode=returncode,
        timed_out=timed_out,
        duration_ms=int((time.monotonic() - started) * 1000),
        error=error,
        command=command,
    )


def _read_lines(stream: TextIO, destination: queue.Queue[str | None]) -> None:
    try:
        for line in stream:
            destination.put(line)
    finally:
        destination.put(None)


def _read_stderr(stream: TextIO, destination: list[str]) -> None:
    destination.extend(stream)
