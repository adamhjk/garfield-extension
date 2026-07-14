package store_test

import (
	"context"
	"testing"
	"time"

	"example.com/ledgerlite/internal/invoice"
	"example.com/ledgerlite/internal/store"
)

func TestDueBeforeIsSortedAndPendingOnly(t *testing.T) {
	repository := store.NewMemory()
	cutoff := time.Date(2026, time.July, 13, 0, 0, 0, 0, time.UTC)
	repository.SeedInvoice(invoice.Invoice{ID: "b", DueAt: cutoff.Add(-time.Hour), Status: invoice.StatusPending})
	repository.SeedInvoice(invoice.Invoice{ID: "a", DueAt: cutoff.Add(-time.Hour), Status: invoice.StatusPending})
	repository.SeedInvoice(invoice.Invoice{ID: "old", DueAt: cutoff.Add(-time.Hour), Status: invoice.StatusExpired})

	got, err := repository.DueBefore(context.Background(), cutoff)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 2 || got[0].ID != "a" || got[1].ID != "b" {
		t.Fatalf("got = %#v", got)
	}
}
