package store

import (
	"context"
	"sort"
	"sync"
	"time"

	"example.com/ledgerlite/internal/audit"
	"example.com/ledgerlite/internal/invoice"
	"example.com/ledgerlite/internal/payment"
)

type Memory struct {
	mu       sync.Mutex
	invoices map[string]invoice.Invoice
	payments map[string]payment.Payment
	audit    []audit.Entry
}

func NewMemory() *Memory {
	return &Memory{
		invoices: make(map[string]invoice.Invoice),
		payments: make(map[string]payment.Payment),
	}
}

func (m *Memory) SeedInvoice(value invoice.Invoice) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.invoices[value.ID] = value
}

func (m *Memory) Invoice(id string) (invoice.Invoice, bool) {
	m.mu.Lock()
	defer m.mu.Unlock()
	value, ok := m.invoices[id]
	return value, ok
}

func (m *Memory) DueBefore(_ context.Context, before time.Time) ([]invoice.Invoice, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	result := make([]invoice.Invoice, 0)
	for _, candidate := range m.invoices {
		if candidate.Status == invoice.StatusPending && candidate.DueAt.Before(before) {
			result = append(result, candidate)
		}
	}
	sort.Slice(result, func(i, j int) bool { return result[i].ID < result[j].ID })
	return result, nil
}

func (m *Memory) SaveInvoice(_ context.Context, value invoice.Invoice) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.invoices[value.ID] = value
	return nil
}

func (m *Memory) SavePayment(_ context.Context, value payment.Payment) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.payments[value.ID] = value
	return nil
}

func (m *Memory) Payment(id string) (payment.Payment, bool) {
	m.mu.Lock()
	defer m.mu.Unlock()
	value, ok := m.payments[id]
	return value, ok
}

func (m *Memory) RecordAudit(_ context.Context, entry audit.Entry) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.audit = append(m.audit, entry)
	return nil
}

func (m *Memory) AuditEntries() []audit.Entry {
	m.mu.Lock()
	defer m.mu.Unlock()
	return append([]audit.Entry(nil), m.audit...)
}
