# Garfield benchmark

Completed runs: 4

| Case | Treatment | Success | Raw tree tokens | Uncached input | Cached input | Output | Coordinator | Delegated | Agents | Wall ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| contained-dry-run | garfield | 1/1 | 4639565 | 352762 | 4234752 | 52051 | 2359497 | 2280068 | 23 | 765740 |
| contained-dry-run | workflow-garfield | 1/1 | 506484 | 87284 | 403200 | 16000 | 506484 | 0 | 3 | 395848 |
| payment-idempotency | garfield | 0/1 | 12277282 | 936219 | 11180032 | 161031 | 6065470 | 6211812 | 45 | 1814578 |
| payment-idempotency | workflow-garfield | 0/1 | 1570242 | 238314 | 1293312 | 38616 | 1570242 | 0 | 6 | 631774 |

## Amortization

Insufficient paired data for amortization.

## Limitations

- cold-to-first-review and resume-to-first-useful-action token boundaries are null when the runtime does not emit token checkpoints at collaboration events
- qualitative patch comparison is intentionally separate from deterministic grading
- raw tree tokens equal input plus output; cached input is a subset of input, is not added twice, and is reported separately from uncached input
