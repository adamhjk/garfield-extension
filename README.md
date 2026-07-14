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

## Project

This extension is based on the original Garfield agent skill in
[dcramer/agents](https://github.com/dcramer/agents). See
[`skills/garfield`](https://github.com/dcramer/agents/tree/main/skills/garfield)
for the skill. This repository is licensed under the
[Apache License 2.0](LICENSE).
