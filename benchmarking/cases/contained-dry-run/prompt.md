Add `--dry-run` to `ledgerctl invoices expire`. It must report what would
expire without changing invoices or recording audit events. Preserve existing
output and exit behavior when the flag is absent.

The implementation slice is already present. Review it, fix only defects in
the requested behavior, and finish with the repository's aggregate validation.
