package audit

import "time"

// Entry records a durable domain action.
type Entry struct {
	Kind        string
	AggregateID string
	AccountID   string
	At          time.Time
}
