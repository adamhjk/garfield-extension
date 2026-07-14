---
name: storage-invariants
description: Use when ledgerlite invoice/payment persistence, idempotency, account scoping, mutation, replay behavior, or audit recording changes.
---

# Storage invariants

Check operations atomically from the caller's perspective. Account-owned keys
must include the account in their storage identity. A replay that returns an
existing result must not repeat mutations or audit events. A dry run performs
no persistence and records no audit entry.
