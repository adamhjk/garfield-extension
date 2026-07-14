# Garfield workflow extension

`@adam/garfield` reviews a pending code change, repairs material defects,
validates the result, and independently reviews it again. It edits the target
working tree without committing and persists its plan, findings, validation, and
token usage as Swamp resources.

## Quickstart

### Before you start

You need:

- the `swamp` CLI;
- an installed and authenticated Codex CLI;
- a Git workspace containing the change to review;
- an executable aggregate validation script in that workspace. The default is
  `./tools/validate.sh`.

The Swamp repository and target workspace may be different directories.

### 1. Create the input file

Create `garfield-input.yaml` in the Swamp repository:

```yaml
runId: invoices-dry-run-20260714-01
workItem: invoices-dry-run
workspaceDir: /home/alice/src/ledgerlite
intent: |
  Add --dry-run to `ledgerctl invoices expire`.
  In dry-run mode, report matching invoices without changing invoice state or
  writing audit events. Without the flag, preserve existing output,
  persistence, audit behavior, and exit codes.
```

### 2. Validate the workflow

```sh
swamp workflow validate @adam/garfield --json
```

### 3. Run Garfield

```sh
swamp workflow run @adam/garfield \
  --input-file garfield-input.yaml \
  --skip-reports \
  --timeout 2h
```

The workflow edits `workspaceDir` directly. Review the resulting Git diff and
commit it through your normal process.

### 4. Inspect the result

```sh
swamp workflow history get @adam/garfield --json
```

For detailed review and accounting resources, see
[Inspect logs and resources](#inspect-logs-and-resources).

## How-to guides

### Use a source checkout

Run Swamp from the root of this repository:

```sh
swamp model type search garfield --json
swamp workflow get @adam/garfield --json
```

Swamp discovers the model under `extensions/models/` and the workflow under
`workflows/`.

### Install from the Swamp registry

If the extension has been published to the registry:

```sh
swamp extension trust add adam
swamp extension pull @adam/garfield
```

After cloning a repository whose lockfile already contains the extension, use
`swamp extension install` to restore its source files.

### Write a useful intent

Treat `intent` as the behavioral contract. State what must change, what must
remain compatible, exact outputs or APIs when relevant, required side effects,
and boundaries the repair must not cross. Example:

```text
Add --dry-run to `ledgerctl invoices expire`. Report zero, one, or many
matches with the existing count grammar. Do not change invoice state, persist
records, write audit entries, or access the mutation clock. Without the flag,
preserve existing output, mutations, audit cardinality, errors, and exit codes.
```

Garfield fixes material problems caused by the current change. It defers
speculative and out-of-scope improvements.

### Inspect logs and resources

View the latest run and logs:

```sh
swamp workflow history get @adam/garfield --json
swamp workflow history logs @adam/garfield --json
```

List or read the model resources:

```sh
swamp data list workflow-garfield --type resource --json
swamp data get workflow-garfield <resource-name> --json
```

Resources beginning with `checkpoint-` contain resumable loop state. Resources
beginning with `result-` contain terminal passed or blocked results.

## Reference

### Inputs

| Input                    | Required | Default               | Meaning                                                 |
| ------------------------ | -------- | --------------------- | ------------------------------------------------------- |
| `runId`                  | yes      | —                     | Caller-visible identifier stored in the result.         |
| `workItem`               | yes      | —                     | Stable identifier used to name checkpoints and results. |
| `workspaceDir`           | yes      | —                     | Path to the target Git workspace.                       |
| `intent`                 | yes      | —                     | Behavioral contract for review and repair.              |
| `validationProgram`      | no       | `./tools/validate.sh` | Aggregate validation executable.                        |
| `validationArgs`         | no       | `[]`                  | Arguments for the validation program.                   |
| `codexPath`              | no       | `codex`               | Codex executable path or command name.                  |
| `model`                  | no       | `configured-default`  | Explicit model or the Codex CLI default.                |
| `reasoningEffort`        | no       | `high`                | `minimal`, `low`, `medium`, `high`, or `xhigh`.         |
| `agentTimeoutMs`         | no       | `1800000`             | Per-review or per-repair timeout.                       |
| `maxActorCalls`          | no       | `2`                   | Repair-process limit; allowed range is 0–2.             |
| `maxReviewCalls`         | no       | `16`                  | Total review-process limit; allowed range is 1–20.      |
| `maxConcurrentReviewers` | no       | `3`                   | Parallel review limit; allowed range is 1–3.            |

Use a new `workItem` for an independent run. Reusing one enables checkpoint
recovery and snapshot-aware idempotency. A passed result for the same work item
and snapshot is returned without another Codex call.

The per-process setting is `agentTimeoutMs`. The CLI `--timeout` applies to the
entire workflow and should be larger.

### Execution behavior

Garfield validates a Git snapshot, selects applicable review lenses, and runs
independent read-only reviewers. Accepted findings go to a workspace-writing
repair process followed by a new snapshot, validation, and review.

Review breadth depends on the change:

| Risk    | Review shape                                                                                   |
| ------- | ---------------------------------------------------------------------------------------------- |
| Simple  | One comprehensive reviewer covers every applicable lens.                                       |
| Medium  | Contract, implementation, and evidence reviewers.                                              |
| Complex | Base reviewers plus applicable interface, state, generated/dependency, and policy specialists. |

Complex or contract-sensitive clear results receive final verification. Review
can cover behavior, compatibility, boundaries, failures, output, side effects,
instructions, tests, policies, documentation, interfaces, generated artifacts,
dependencies, dead code, and implementation minimalism.

### Result fields

| Field                       | Meaning                                                                     |
| --------------------------- | --------------------------------------------------------------------------- |
| `status`                    | `passed` or `blocked`.                                                      |
| `reason`                    | Terminal reason for the result.                                             |
| `snapshot`                  | Final hash, changed paths, bounded diff, and truncation status.             |
| `plan`                      | Risk, applicable lenses, assignments, and instruction/policy paths.         |
| `validation`                | Final command, exit code, duration, bounded output, and pass status.        |
| `reviews`                   | Structured reviews grouped by cycle and assignment.                         |
| `decisions`                 | Accepted, rejected, and deferred findings with rationales.                  |
| `invocations`               | Per-process role, assignment, outcome, duration, previews, and token usage. |
| `usage`                     | Aggregate input, cached input, output, reasoning output, and total tokens.  |
| `actorCalls` / `agentCalls` | Repair count and total Codex process count.                                 |

`cachedInputTokens` is a subset of `inputTokens`. `totalTokens` is input plus
output; cached input is not counted twice.

### Passed and blocked runs

A run passes when aggregate validation succeeds and the final applicable reviews
are clear after adjudication.

A blocked run persists its checkpoint and result, then fails the workflow step.
Typical causes are validation failure, exhausted budgets, recurring findings,
failed Codex processes, sensitive changes, or incompatible workspace drift.

Retry with the same `workItem` only after inspecting the result and logs. The
checkpoint is reused only when it is compatible with the current snapshot.

### Workspace safety

- Reviews use a read-only Codex sandbox; repairs use workspace-write.
- Nested agents are disabled.
- Repairs are instructed not to reset, revert, or commit.
- Protected and common secret paths are rejected.
- Persisted validation and Codex previews are bounded and redact common secret
  patterns.
- The validation executable must resolve inside the workspace.

Garfield preserves the existing working copy rather than creating a clean one.
Review the final diff even when the run passes.

## Troubleshooting

### The model or workflow is not found

```sh
swamp doctor extensions --json
swamp model type search garfield --json
swamp workflow get @adam/garfield --json
```

For a registry installation, confirm that `adam` is trusted and pull the
extension again.

### Validation fails

Run the configured command directly from the target workspace. Repair the script
itself only if the current change made it stale or invalid.

### The run times out

Increase both `agentTimeoutMs` and the whole-workflow `--timeout`. The latter
must cover validation and every sequential review/repair cycle.

### The workflow fails after Codex returns output

Read the persisted `result-*` resource. Garfield fails closed when a Codex
response does not satisfy its structured contract or cannot be fully accounted.

## Benchmarking

This extension is benchmarked head-to-head against the original Garfield skill on
identical workspaces, graded by an objective oracle that runs public validation,
hidden behavioral tests, a changed-path allowlist, and a change-size budget.

### Result

Measured 2026-07-14 with Codex CLI 0.144.3 at `high` reasoning effort. One
repetition per treatment per case.

| Case                  | Treatment           | Graded | Tree tokens | Agents | Wall     |
| --------------------- | ------------------- | ------ | ----------: | -----: | -------: |
| `contained-dry-run`   | skill               | pass   |   4,639,565 |     23 | 12.8 min |
| `contained-dry-run`   | **extension**       | pass   | **506,484** |      3 |  6.6 min |
| `payment-idempotency` | skill               | fail   |  12,277,282 |     45 | 30.2 min |
| `payment-idempotency` | **extension**       | fail   | **1,570,242** |    6 | 10.5 min |

The extension reached the same graded outcome as the skill on both cases while
spending **8.1x fewer tokens** overall (2.1M against 16.9M) and finishing 2-3x
faster. "Tree tokens" is the complete agent-tree cost — every session the
treatment spawned, input plus output.

Two things the pass/fail column does not show, and that matter more than the
token ratio:

- **Neither method solved `payment-idempotency`.** Both repaired three of its four
  seeded defects and both left the same one — an undocumented HTTP 409 error shape
  — so both fail the same hidden test. The case discriminates against both.
- **They failed differently.** The skill failed *open*: it terminated with
  `garfield: pass`, "Independent verification: verified", "Residual/deferred
  concerns: none" — a false clear, with the defect still in the diff — and it
  overshot the change budget. The extension failed *closed*: it exhausted its
  repair budget and stopped with `status: blocked`, `reason:
  findings_remain_after_actor_limit`, explicitly reporting unresolved findings,
  and stayed inside the budget. For a review-and-repair tool, stopping and saying
  "findings remain" beats reporting done with a defect in the diff.

The full report, the diff each treatment produced, per-assertion grading evidence,
and per-session token accounting are stored in
[`benchmarking/results/`](benchmarking/results/README.md).

### Run it yourself

You need an authenticated Codex CLI, the `swamp` CLI, Go, and Python 3.12+. The
benchmark base (`benchmarking/ledgerlite`) is vendored, so no external checkout is
needed for the extension. Comparing against the skill additionally needs a
checkout of [dcramer/agents](https://github.com/dcramer/agents).

From `benchmarking/`, first verify the harness and fixtures:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src python3 -m garfield_bench.cli verify-fixtures --base ledgerlite
```

Then run each treatment against the same case, into a shared runs directory:

```sh
PYTHONPATH=src python3 -m garfield_bench.cli run-one \
  --treatment workflow-garfield --case contained-dry-run \
  --base ledgerlite \
  --calibration calibration/current-runtime.json \
  --runs runs-comparison

PYTHONPATH=src python3 -m garfield_bench.cli run-one \
  --treatment garfield --case contained-dry-run \
  --base ledgerlite --agents-repo /path/to/dcramer-agents \
  --calibration calibration/current-runtime.json \
  --runs runs-comparison
```

Repeat both commands with `--case payment-idempotency`, then aggregate:

```sh
PYTHONPATH=src python3 -m garfield_bench.cli report \
  --runs runs-comparison --output results
```

`run-one` exits non-zero when a run fails its grade, which is a legitimate
benchmark outcome — do not treat it as a harness error. A failed grade is
explained by `runs-comparison/<run-id>/grading.json`.

The harness, fixtures, telemetry calibration, and the full set of commands are
documented in [`benchmarking/`](benchmarking/README.md).

## Project

This extension is based on the original Garfield agent skill in
[dcramer/agents](https://github.com/dcramer/agents). See
[`skills/garfield`](https://github.com/dcramer/agents/tree/main/skills/garfield)
for the skill. This repository is licensed under the
[Apache License 2.0](LICENSE).
