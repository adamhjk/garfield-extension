# Telemetry calibration

`current-runtime.json` records the passing Phase 1 result observed with Codex
CLI 0.144.3 on 2026-07-13. The app-server JSONL stream contains one root and one
spawned child, separate exclusive token updates for both threads, and explicit
parent linkage from the child activity event.

The recorded response deltas sum to 95,887 tokens: 50,203 for the coordinator
and 45,684 for the child. That sum exactly matches the independent cumulative
runtime ledger. Cached input and reasoning output remain separate diagnostic
fields and are not added to `total_tokens` a second time.

Replace this evidence only by running:

```sh
PYTHONPATH=src python -m garfield_bench.cli calibrate \
  --output calibration/current-runtime.json
```

A passing result must contain exactly one root and one child session. Every
session must have a parent link where applicable and complete token usage, and
the summed per-response deltas must equal the cumulative runtime ledger. Do not
manually flip `passed`.
