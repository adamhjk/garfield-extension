package main

import (
	"bytes"
	"context"
	"testing"
	"time"

	"example.com/ledgerlite/internal/invoice"
)

type hiddenZeroExpirer struct{}

func (hiddenZeroExpirer) Expire(context.Context, time.Time, bool) ([]invoice.Invoice, error) {
	return nil, nil
}

func TestHiddenDryRunZeroMatchOutput(t *testing.T) {
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	exitCode := run([]string{
		"invoices", "expire", "--before", "2026-07-13T12:00:00Z", "--dry-run",
	}, &stdout, &stderr, hiddenZeroExpirer{})
	if exitCode != 0 {
		t.Fatalf("exit = %d, stderr = %q", exitCode, stderr.String())
	}
	if got := stdout.String(); got != "would expire 0 invoices\n" {
		t.Fatalf("stdout = %q", got)
	}
}
