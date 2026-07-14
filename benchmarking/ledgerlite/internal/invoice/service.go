package invoice

import (
	"context"
	"time"

	"example.com/ledgerlite/internal/audit"
)

type Service struct {
	repository Repository
	now        func() time.Time
}

func NewService(repository Repository, now func() time.Time) *Service {
	return &Service{repository: repository, now: now}
}

func (s *Service) Expire(ctx context.Context, before time.Time) ([]Invoice, error) {
	invoices, err := s.repository.DueBefore(ctx, before)
	if err != nil {
		return nil, err
	}

	for i := range invoices {
		invoices[i].Status = StatusExpired
		if err := s.repository.SaveInvoice(ctx, invoices[i]); err != nil {
			return nil, err
		}
		if err := s.repository.RecordAudit(ctx, audit.Entry{
			Kind:        "invoice.expired",
			AggregateID: invoices[i].ID,
			AccountID:   invoices[i].AccountID,
			At:          s.now(),
		}); err != nil {
			return nil, err
		}
	}

	return invoices, nil
}
