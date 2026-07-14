# Testing

Behavior changes require a focused package test. Storage behavior must test
account scoping and audit cardinality when either can change. CLI tests assert
exact stdout, stderr, exit status, and mutation behavior relevant to the slice.
