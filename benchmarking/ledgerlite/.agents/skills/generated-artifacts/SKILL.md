---
name: generated-artifacts
description: Use when ledgerlite OpenAPI, schemas, generated client code, or generator behavior changes or a generated artifact may be stale.
---

# Generated artifacts

Treat `api/openapi.json` as the source and `generated/client.go` as derived.
Run `go run ./tools/generate -check`; if stale, update the source as needed and
regenerate with `go run ./tools/generate`. Never repair generated output by
hand.
