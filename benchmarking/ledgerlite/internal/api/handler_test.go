package api_test

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"example.com/ledgerlite/internal/api"
	"example.com/ledgerlite/internal/payment"
	"example.com/ledgerlite/internal/store"
)

func TestCreatePayment(t *testing.T) {
	repository := store.NewMemory()
	service := payment.NewService(repository, func() string { return "pay-1" }, time.Now)
	handler := api.NewHandler(service)

	request := httptest.NewRequest(http.MethodPost, "/accounts/acct-1/payments", bytes.NewBufferString(`{"amount":1250,"currency":"USD"}`))
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)

	if response.Code != http.StatusCreated {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	if got := response.Header().Get("Content-Type"); got != "application/json" {
		t.Fatalf("content type = %q", got)
	}
}
