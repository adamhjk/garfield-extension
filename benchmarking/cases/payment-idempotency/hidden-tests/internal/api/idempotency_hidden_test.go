package api_test

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"example.com/ledgerlite/internal/api"
	"example.com/ledgerlite/internal/payment"
	"example.com/ledgerlite/internal/store"
)

func TestHiddenConflictUsesDocumentedErrorShape(t *testing.T) {
	repository := store.NewMemory()
	service := payment.NewService(repository, func() string { return "pay-1" }, time.Now)
	handler := api.NewHandler(service)

	first := httptest.NewRequest(http.MethodPost, "/accounts/acct-1/payments", bytes.NewBufferString(`{"amount":100,"currency":"USD"}`))
	first.Header.Set("Idempotency-Key", "key-1")
	handler.ServeHTTP(httptest.NewRecorder(), first)

	conflict := httptest.NewRequest(http.MethodPost, "/accounts/acct-1/payments", bytes.NewBufferString(`{"amount":200,"currency":"USD"}`))
	conflict.Header.Set("Idempotency-Key", "key-1")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, conflict)

	if response.Code != http.StatusConflict {
		t.Fatalf("status = %d", response.Code)
	}
	var body map[string]string
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if len(body) != 2 || body["code"] != "idempotency_conflict" || body["message"] != "idempotency key conflicts with an existing payment" {
		t.Fatalf("body = %#v", body)
	}
}
