package invoice

import (
	"context"
	"time"

	"example.com/ledgerlite/internal/audit"
)

type Status string

const (
	StatusPending Status = "pending"
	StatusExpired Status = "expired"
)

type Invoice struct {
	ID        string
	AccountID string
	DueAt     time.Time
	Status    Status
}

type Repository interface {
	DueBefore(context.Context, time.Time) ([]Invoice, error)
	SaveInvoice(context.Context, Invoice) error
	RecordAudit(context.Context, audit.Entry) error
}
