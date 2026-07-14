# Stored benchmark result

This directory holds a committed benchmark result comparing the original
Garfield **skill** (`garfield`) against this repository's Garfield **workflow
extension** (`workflow-garfield`).

## Provenance

| Property        | Value                                                        |
| --------------- | ------------------------------------------------------------ |
| Date            | 2026-07-14                                                   |
| Cases           | `contained-dry-run`, `payment-idempotency`                   |
| Repetitions     | 1 per treatment per case (4 runs)                            |
| Codex CLI       | 0.144.3                                                      |
| Swamp CLI       | 20260615.105123.0                                            |
| Go              | 1.26.5                                                       |
| Reasoning effort| `high`                                                       |
| Model           | Codex CLI configured default                                 |
| Base            | `benchmarking/ledgerlite`                                    |
| Skill source    | [dcramer/agents](https://github.com/dcramer/agents) `skills/garfield` |
| Calibration     | `calibration/current-runtime.json`                           |

Both treatments started from a byte-identical workspace tree per case, and both
were graded by the same objective oracle.

## Files

- `report.json`, `report.md`, `report.html` — generated aggregate report.
- `evidence/<run-id>/final.patch` — the diff each treatment produced.
- `evidence/<run-id>/grading.json` — per-assertion grading evidence.
- `evidence/<run-id>/usage.jsonl` — per-agent-session token accounting.
- `evidence/<run-id>/result.json` — run status, blocker, and workspace hash.

(The directory is named `evidence/`, not `runs/`, because `.gitignore` excludes
`runs*/` — generated run workspaces must stay untracked.)

## Reading the numbers

**Raw tree tokens** is the complete agent-tree cost: every agent session the
treatment spawned, input plus output. Cached input is a subset of input and is
never counted twice.

**The `Coordinator` / `Delegated` split is only meaningful for the skill.** The
skill runs a coordinator agent that delegates to sub-agents, so its cost divides
across both columns. The extension is coordinator-free — its adapter records each
workflow invocation as a root session with no parent — so all of its tokens land
in the `Coordinator` column and `Delegated` reads `0`. That is a bookkeeping
artifact, not a claim that the extension spends its budget on a coordinator. The
tree total is correct for both.

**Amortization is empty by design.** That section compares `garfield` against
`swamp-garfield`, which is not one of the treatments run here.

## Caveats

- **n=1 per cell.** These are single repetitions. They are enough to show an
  order-of-magnitude cost difference, but not to characterize variance. Use
  `--repetitions` for that.
- **Wall clock is not isolated.** Runs were sequential on one workstation, but
  no CPU pinning was used and agent latency depends on upstream service load.
- **Neither treatment solved `payment-idempotency`.** See below — the cheaper
  treatment is not the more accurate one on that case.

## Results

| Case                  | Treatment           | Graded | Tree tokens | Agents | Wall     |
| --------------------- | ------------------- | ------ | ----------: | -----: | -------: |
| `contained-dry-run`   | `garfield`          | pass   |   4,639,565 |     23 | 12.8 min |
| `contained-dry-run`   | `workflow-garfield` | pass   |     506,484 |      3 |  6.6 min |
| `payment-idempotency` | `garfield`          | fail   |  12,277,282 |     45 | 30.2 min |
| `payment-idempotency` | `workflow-garfield` | fail   |   1,570,242 |      6 | 10.5 min |

The extension reached the same graded outcome as the skill on both cases while
spending **8.1x fewer tokens overall** (2.1M vs 16.9M) and running roughly 2-3x
faster.

### `contained-dry-run`: both pass

Both treatments removed both seeded defects and passed every assertion.

### `payment-idempotency`: both fail, on the same defect

This case seeds four defects. Both treatments repaired three of them — including
regenerating the stale `generated/client.go` — and both left the fourth: the HTTP
409 response keeps an undocumented error object. Both runs therefore fail the
same hidden test, `TestHiddenConflictUsesDocumentedErrorShape`. The case is
discriminating against both methods, not against one.

The two failures are not equivalent in character:

- **The skill failed open.** Its coordinator terminated with an explicit clear:

  ```text
  garfield: pass
  ...
  - Independent verification: verified
  - Residual/deferred concerns: none
  ```

  It reported "none" while the defect was still in the diff. It also overshot the
  change budget (395 changed lines against a 360-line limit, across 10 files).
- **The extension failed closed.** It exhausted its repair budget and returned
  `status: blocked`, `reason: findings_remain_after_actor_limit`, explicitly
  reporting unresolved findings rather than declaring success. It stayed within
  the change budget (301 lines, 11 files).

For a review-and-repair tool, a run that stops and says "findings remain" is more
useful than one that reports done with a defect still in the diff. That
distinction is not captured by the pass/fail column, which is why it is recorded
here.
