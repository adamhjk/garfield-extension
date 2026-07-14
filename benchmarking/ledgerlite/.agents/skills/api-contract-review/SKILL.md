---
name: api-contract-review
description: Use when ledgerlite HTTP handlers, status codes, request headers, JSON serialization, OpenAPI, or the generated client change or should change.
---

# API contract review

Compare handler behavior, `api/openapi.json`, public tests, and
`generated/client.go`. Preserve exact status and error serialization unless the
slice explicitly changes them. Apply `policies/api-compatibility.md` and report
stale generated output as a material finding.
