package main

import (
	"bytes"
	"context"
	"testing"
	"time"

	"example.com/ledgerlite/internal/invoice"
)

type stubExpirer struct {
	result []invoice.Invoice
	before time.Time
}

func (s *stubExpirer) Expire(_ context.Context, before time.Time) ([]invoice.Invoice, error) {
	s.before = before
	return s.result, nil
}

func TestExpireCommandPreservesOutput(t *testing.T) {
	expirer := &stubExpirer{result: []invoice.Invoice{{ID: "inv-1"}}}
	var stdout bytes.Buffer
	var stderr bytes.Buffer

	exitCode := run([]string{"invoices", "expire", "--before", "2026-07-13T12:00:00Z"}, &stdout, &stderr, expirer)
	if exitCode != 0 {
		t.Fatalf("exit = %d, stderr = %q", exitCode, stderr.String())
	}
	if got := stdout.String(); got != "expired 1 invoice\n" {
		t.Fatalf("stdout = %q", got)
	}
}
