package invoice_test

import (
	"context"
	"testing"
	"time"

	"example.com/ledgerlite/internal/invoice"
	"example.com/ledgerlite/internal/store"
)

func TestExpireUpdatesDueInvoicesAndRecordsAudit(t *testing.T) {
	now := time.Date(2026, time.July, 13, 12, 0, 0, 0, time.UTC)
	repository := store.NewMemory()
	repository.SeedInvoice(invoice.Invoice{
		ID: "inv-1", AccountID: "acct-1", DueAt: now.Add(-time.Hour), Status: invoice.StatusPending,
	})
	repository.SeedInvoice(invoice.Invoice{
		ID: "inv-2", AccountID: "acct-1", DueAt: now.Add(time.Hour), Status: invoice.StatusPending,
	})

	service := invoice.NewService(repository, func() time.Time { return now })
	expired, err := service.Expire(context.Background(), now)
	if err != nil {
		t.Fatal(err)
	}
	if len(expired) != 1 || expired[0].ID != "inv-1" {
		t.Fatalf("expired = %#v", expired)
	}
	stored, _ := repository.Invoice("inv-1")
	if stored.Status != invoice.StatusExpired {
		t.Fatalf("status = %q", stored.Status)
	}
	if got := len(repository.AuditEntries()); got != 1 {
		t.Fatalf("audit entries = %d", got)
	}
}
