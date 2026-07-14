package invoice_test

import (
	"context"
	"testing"
	"time"

	"example.com/ledgerlite/internal/invoice"
	"example.com/ledgerlite/internal/store"
)

func TestHiddenDryRunWritesNoAuditEvent(t *testing.T) {
	now := time.Date(2026, time.July, 13, 12, 0, 0, 0, time.UTC)
	repository := store.NewMemory()
	repository.SeedInvoice(invoice.Invoice{
		ID: "inv-hidden", AccountID: "acct-hidden", DueAt: now.Add(-time.Minute), Status: invoice.StatusPending,
	})
	service := invoice.NewService(repository, func() time.Time { return now })

	if _, err := service.Expire(context.Background(), now, true); err != nil {
		t.Fatal(err)
	}
	if got := len(repository.AuditEntries()); got != 0 {
		t.Fatalf("dry-run audit entries = %d, want 0", got)
	}
}
