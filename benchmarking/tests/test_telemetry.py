from __future__ import annotations

import json
import unittest

from garfield_bench.telemetry import (
    CodexAppServerCollector,
    CodexJSONLCollector,
    TelemetryError,
    calibrate_events,
)


class TelemetryTests(unittest.TestCase):
    def test_root_turn_usage_is_exact_and_cached_is_separate(self) -> None:
        collector = CodexJSONLCollector("run-1")
        collector.consume_lines(
            [
                json.dumps({"type": "thread.started", "thread_id": "root"}),
                json.dumps(
                    {
                        "type": "turn.completed",
                        "turn_id": "turn-1",
                        "usage": {
                            "input_tokens": 100,
                            "cached_input_tokens": 40,
                            "output_tokens": 20,
                            "reasoning_output_tokens": 5,
                        },
                    }
                ),
            ]
        )
        [row] = collector.rows()
        self.assertEqual(row.total_tokens, 120)
        self.assertEqual(row.cached_input_tokens, 40)
        self.assertEqual(row.reasoning_output_tokens, 5)

    def test_duplicate_turn_is_not_double_counted(self) -> None:
        event = json.dumps(
            {
                "type": "turn.completed",
                "thread_id": "root",
                "turn_id": "same",
                "usage": {"input_tokens": 10, "output_tokens": 2},
            }
        )
        collector = CodexJSONLCollector("run-1")
        collector.consume_lines(
            [json.dumps({"type": "thread.started", "thread_id": "root"}), event, event]
        )
        self.assertEqual(collector.rows()[0].total_tokens, 12)

    def test_parent_child_calibration_reconciles(self) -> None:
        events = [
            json.dumps({"type": "thread.started", "thread_id": "root"}),
            json.dumps(
                {
                    "type": "agent.usage",
                    "agent_id": "child",
                    "parent_agent_id": "root",
                    "usage_id": "child-final",
                    "usage": {"input_tokens": 30, "output_tokens": 5},
                }
            ),
            json.dumps(
                {
                    "type": "turn.completed",
                    "thread_id": "root",
                    "turn_id": "root-final",
                    "usage": {"input_tokens": 50, "output_tokens": 10},
                }
            ),
        ]
        result = calibrate_events(events, runtime_tree_total=95)
        self.assertTrue(result.passed, result.reason)
        self.assertEqual(result.computed_tree_total, 95)

    def test_mixed_session_counting_is_rejected(self) -> None:
        collector = CodexJSONLCollector("run-1")
        collector.consume({"type": "thread.started", "thread_id": "root"})
        collector.consume(
            {
                "type": "turn.completed",
                "thread_id": "root",
                "turn_id": "one",
                "usage": {"input_tokens": 10, "output_tokens": 2},
            }
        )
        with self.assertRaises(TelemetryError):
            collector.consume(
                {
                    "type": "agent.usage",
                    "agent_id": "root",
                    "usage_id": "final",
                    "usage": {"input_tokens": 10, "output_tokens": 2},
                }
            )

    def test_calibration_fails_closed_without_child(self) -> None:
        events = [
            json.dumps({"type": "thread.started", "thread_id": "root"}),
            json.dumps(
                {
                    "type": "turn.completed",
                    "thread_id": "root",
                    "usage": {"input_tokens": 50, "output_tokens": 10},
                }
            ),
        ]
        result = calibrate_events(events, runtime_tree_total=60)
        self.assertFalse(result.passed)
        self.assertIn("one parent and one child", result.reason)

    def test_app_server_accounts_root_child_and_grandchild_exclusively(self) -> None:
        collector = CodexAppServerCollector("run-1")
        collector.register_thread("root", root=True)
        collector.consume(_subagent_started("root", "child", "/root/review_api"))
        collector.consume(_subagent_started("child", "grandchild", "/root/verify_api"))
        collector.consume(_usage_update("root", "root-turn", 10, 4, 2, 1))
        collector.consume(_usage_update("root", "root-turn", 17, 9, 3, 1, previous=(10, 4, 2, 1)))
        collector.consume(_usage_update("child", "child-turn", 20, 8, 5, 2))
        collector.consume(_usage_update("grandchild", "grandchild-turn", 7, 2, 1, 0))
        collector.validate_complete_tree()

        rows = {row.agent_id: row for row in collector.rows()}
        self.assertEqual(rows["root"].total_tokens, 20)
        self.assertEqual(rows["child"].total_tokens, 25)
        self.assertEqual(rows["grandchild"].total_tokens, 8)
        self.assertEqual(rows["child"].parent_agent_id, "root")
        self.assertEqual(rows["grandchild"].parent_agent_id, "child")
        self.assertEqual(rows["child"].stage, "review")
        self.assertEqual(rows["grandchild"].stage, "verification")
        self.assertEqual(collector.runtime_tree_total, 53)

    def test_app_server_duplicate_usage_notification_is_idempotent(self) -> None:
        collector = CodexAppServerCollector("run-1")
        collector.register_thread("root", root=True)
        event = _usage_update("root", "turn", 10, 4, 2, 1)
        collector.consume(event)
        collector.consume(event)
        self.assertEqual(collector.rows()[0].total_tokens, 12)
        self.assertEqual(collector.runtime_tree_total, 12)

    def test_app_server_rejects_delta_that_disagrees_with_runtime_total(self) -> None:
        collector = CodexAppServerCollector("run-1")
        collector.register_thread("root", root=True)
        event = _usage_update("root", "turn", 10, 4, 2, 1)
        event["params"]["tokenUsage"]["last"]["inputTokens"] = 9
        event["params"]["tokenUsage"]["last"]["totalTokens"] = 11
        with self.assertRaises(TelemetryError):
            collector.consume(event)

    def test_app_server_rejects_spawned_session_without_usage(self) -> None:
        collector = CodexAppServerCollector("run-1")
        collector.register_thread("root", root=True)
        collector.consume(_subagent_started("root", "child", "/root/review"))
        collector.consume(_usage_update("root", "turn", 10, 4, 2, 1))
        with self.assertRaises(TelemetryError):
            collector.validate_complete_tree()

    def test_app_server_calibration_uses_final_totals_as_runtime_ledger(self) -> None:
        events = [
            json.dumps(_thread_started("root")),
            json.dumps(_subagent_started("root", "child", "/root/calibration_review")),
            json.dumps(_usage_update("root", "root-turn", 10, 4, 2, 1)),
            json.dumps(_usage_update("child", "child-turn", 20, 8, 5, 2)),
        ]
        result = calibrate_events(events)
        self.assertTrue(result.passed, result.reason)
        self.assertEqual(result.computed_tree_total, 37)
        self.assertEqual(result.runtime_tree_total, 37)


def _thread_started(thread_id: str) -> dict[str, object]:
    return {
        "method": "thread/started",
        "params": {"thread": {"id": thread_id, "parentThreadId": None}},
    }


def _subagent_started(parent: str, child: str, path: str) -> dict[str, object]:
    return {
        "method": "item/completed",
        "params": {
            "threadId": parent,
            "turnId": f"{parent}-turn",
            "item": {
                "id": f"spawn-{child}",
                "type": "subAgentActivity",
                "kind": "started",
                "agentThreadId": child,
                "agentPath": path,
            },
        },
    }


def _usage_update(
    thread_id: str,
    turn_id: str,
    input_tokens: int,
    cached_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
    *,
    previous: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> dict[str, object]:
    previous_input, previous_cached, previous_output, previous_reasoning = previous
    total = {
        "inputTokens": input_tokens,
        "cachedInputTokens": cached_tokens,
        "outputTokens": output_tokens,
        "reasoningOutputTokens": reasoning_tokens,
        "totalTokens": input_tokens + output_tokens,
    }
    last = {
        "inputTokens": input_tokens - previous_input,
        "cachedInputTokens": cached_tokens - previous_cached,
        "outputTokens": output_tokens - previous_output,
        "reasoningOutputTokens": reasoning_tokens - previous_reasoning,
        "totalTokens": input_tokens + output_tokens - previous_input - previous_output,
    }
    return {
        "method": "thread/tokenUsage/updated",
        "params": {"threadId": thread_id, "turnId": turn_id, "tokenUsage": {"total": total, "last": last}},
    }


if __name__ == "__main__":
    unittest.main()
