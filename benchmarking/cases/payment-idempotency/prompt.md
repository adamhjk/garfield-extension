Support idempotency keys when creating payments. Repeating the same key and
payload within an account must return the original payment. Reusing the key
with different input must conflict. Keys are scoped per account. Update the
public API contract and generated client.

The implementation slice is already present. Review it, fix only defects in
the requested behavior, and finish with the repository's aggregate validation.
