---
name: repository-testing
description: Use for ledgerlite implementation and review work that changes Go code, tests, validation, CLI behavior, or cross-package behavior. Run the smallest focused test first and the aggregate offline validation before handoff.
---

# Repository testing

Run focused tests for touched packages while iterating. Before handoff run
`./tools/validate.sh` from the repository root. It is the authoritative public
validation entry point and must complete without network access.

Do not treat hidden benchmark tests as repository validation; they are owned by
the external grader and are never present in the working copy.
