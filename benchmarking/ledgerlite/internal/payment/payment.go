package payment

import (
	"context"
	"errors"

	"example.com/ledgerlite/internal/audit"
)

var ErrInvalidRequest = errors.New("invalid payment request")

type CreateRequest struct {
	Amount   int64  `json:"amount"`
	Currency string `json:"currency"`
}

func (r CreateRequest) Valid() bool {
	return r.Amount > 0 && len(r.Currency) == 3
}

type Payment struct {
	ID        string `json:"id"`
	AccountID string `json:"accountId"`
	Amount    int64  `json:"amount"`
	Currency  string `json:"currency"`
}

type Repository interface {
	SavePayment(context.Context, Payment) error
	RecordAudit(context.Context, audit.Entry) error
}
