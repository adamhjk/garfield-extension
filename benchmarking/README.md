# Garfield benchmark

This harness compares the original Garfield skill, the Software Factory-backed
Swamp skill, and the coordinator-free Garfield workflow extension. It creates
byte-identical Ledgerlite workspaces, captures complete agent token usage,
grades changes against public and hidden tests, and produces JSON, Markdown,
and HTML reports.

Generated run workspaces and reports are intentionally excluded from this
repository.

## Requirements

- Python 3.12 or newer;
- an installed and authenticated Codex CLI;
- the `swamp` CLI for workflow treatments;
- Go, for the Ledgerlite validation and grading commands;
- a checkout of [dcramer/agents](https://github.com/dcramer/agents) only when
  running the `garfield` or `swamp-garfield` treatments.

The immutable benchmark base is vendored at [`ledgerlite/`](ledgerlite/), so no
external checkout is needed. Pass it as `--base ledgerlite`. Workspaces are
materialized by copying that tree (excluding `.git`, `.jj`, and `.swamp`),
committing it, and applying the case fixture patch, so the base is never mutated.

A stored result comparing the skill against the workflow extension lives in
[`results/`](results/README.md).

The harness refuses live runs until a parent/child calibration proves that the
installed Codex runtime reports exclusive usage for every agent session.
Root-only totals are never presented as complete tree totals.

## Verify the harness

From `benchmarking/`:

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m garfield_bench.cli verify-fixtures \
  --base ledgerlite
```

## Calibrate token accounting

```sh
PYTHONPATH=src python -m garfield_bench.cli calibrate \
  --output calibration.json
```

The event stream must contain one root and one child, explicit parent linkage,
and exclusive usage for both. The collector reconciles response deltas with
the cumulative runtime ledger and fails closed on missing or mismatched data.

## Run the workflow benchmark

The extension checkout defaults to the parent of `benchmarking/`, so a normal
source checkout does not need `--extension-repo`:

```sh
PYTHONPATH=src python -m garfield_bench.cli run-one \
  --treatment workflow-garfield \
  --case contained-dry-run \
  --base ledgerlite \
  --calibration calibration/current-runtime.json \
  --runs runs-workflow
```

Use `--extension-repo /path/to/garfield-extension` when running the harness
outside its canonical checkout. Coordinator sessions default to a 30-minute
timeout; override that with `--timeout SECONDS`.

## Compare with the original skill

Run each treatment against the same case and repetition:

```sh
PYTHONPATH=src python -m garfield_bench.cli run-one \
  --treatment garfield \
  --case contained-dry-run \
  --base ledgerlite \
  --agents-repo /path/to/dcramer-agents \
  --calibration calibration/current-runtime.json \
  --runs runs-comparison

PYTHONPATH=src python -m garfield_bench.cli run-one \
  --treatment workflow-garfield \
  --case contained-dry-run \
  --base ledgerlite \
  --calibration calibration/current-runtime.json \
  --runs runs-comparison
```

`pilot`, `full`, and `run-pair` retain the original paired
`garfield`/`swamp-garfield` schedule and therefore require `--agents-repo`.

## Produce a report

```sh
PYTHONPATH=src python -m garfield_bench.cli report \
  --runs runs-comparison \
  --output report-comparison
```

Reports split input into uncached and cached portions and report output
separately. Cached input is already part of input and is never added twice.

To prepare patches for qualitative review:

```sh
PYTHONPATH=src python -m garfield_bench.cli prepare-blind \
  --runs runs-comparison \
  --output blind-review
```

Keep `mapping.private.json` away from reviewers until their judgments are
final.
