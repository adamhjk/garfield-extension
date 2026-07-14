package payment_test

import (
	"context"
	"testing"
	"time"

	"example.com/ledgerlite/internal/payment"
	"example.com/ledgerlite/internal/store"
)

func TestHiddenIdempotencyKeysAreScopedPerAccount(t *testing.T) {
	repository := store.NewMemory()
	nextID := 0
	service := payment.NewService(repository, func() string {
		nextID++
		if nextID == 1 {
			return "pay-1"
		}
		return "pay-2"
	}, time.Now)

	if _, err := service.Create(context.Background(), "acct-1", "shared-key", payment.CreateRequest{Amount: 100, Currency: "USD"}); err != nil {
		t.Fatal(err)
	}
	second, err := service.Create(context.Background(), "acct-2", "shared-key", payment.CreateRequest{Amount: 200, Currency: "USD"})
	if err != nil {
		t.Fatalf("second account create: %v", err)
	}
	if second.ID != "pay-2" || second.AccountID != "acct-2" {
		t.Fatalf("second = %#v", second)
	}
}

func TestHiddenReplayDoesNotDuplicateAudit(t *testing.T) {
	repository := store.NewMemory()
	service := payment.NewService(repository, func() string { return "pay-1" }, time.Now)
	request := payment.CreateRequest{Amount: 100, Currency: "USD"}

	if _, err := service.Create(context.Background(), "acct-1", "key-1", request); err != nil {
		t.Fatal(err)
	}
	if _, err := service.Create(context.Background(), "acct-1", "key-1", request); err != nil {
		t.Fatal(err)
	}
	if got := len(repository.AuditEntries()); got != 1 {
		t.Fatalf("audit entries = %d, want 1", got)
	}
}
