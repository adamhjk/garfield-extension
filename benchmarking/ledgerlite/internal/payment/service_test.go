package payment_test

import (
	"context"
	"testing"
	"time"

	"example.com/ledgerlite/internal/payment"
	"example.com/ledgerlite/internal/store"
)

func TestCreatePayment(t *testing.T) {
	repository := store.NewMemory()
	service := payment.NewService(repository, func() string { return "pay-1" }, time.Now)

	created, err := service.Create(context.Background(), "acct-1", payment.CreateRequest{
		Amount: 1250, Currency: "USD",
	})
	if err != nil {
		t.Fatal(err)
	}
	if created.ID != "pay-1" || created.AccountID != "acct-1" {
		t.Fatalf("created = %#v", created)
	}
	if got := len(repository.AuditEntries()); got != 1 {
		t.Fatalf("audit entries = %d", got)
	}
}
