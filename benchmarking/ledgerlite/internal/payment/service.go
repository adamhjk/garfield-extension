package payment

import (
	"context"
	"time"

	"example.com/ledgerlite/internal/audit"
)

type Service struct {
	repository Repository
	newID      func() string
	now        func() time.Time
}

func NewService(repository Repository, newID func() string, now func() time.Time) *Service {
	return &Service{repository: repository, newID: newID, now: now}
}

func (s *Service) Create(ctx context.Context, accountID string, request CreateRequest) (Payment, error) {
	if accountID == "" || !request.Valid() {
		return Payment{}, ErrInvalidRequest
	}

	created := Payment{
		ID:        s.newID(),
		AccountID: accountID,
		Amount:    request.Amount,
		Currency:  request.Currency,
	}
	if err := s.repository.SavePayment(ctx, created); err != nil {
		return Payment{}, err
	}
	if err := s.repository.RecordAudit(ctx, audit.Entry{
		Kind:        "payment.created",
		AggregateID: created.ID,
		AccountID:   accountID,
		At:          s.now(),
	}); err != nil {
		return Payment{}, err
	}
	return created, nil
}
