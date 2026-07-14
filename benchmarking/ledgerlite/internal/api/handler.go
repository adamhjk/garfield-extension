package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"example.com/ledgerlite/internal/payment"
)

type paymentCreator interface {
	Create(context.Context, string, payment.CreateRequest) (payment.Payment, error)
}

type Handler struct {
	payments paymentCreator
}

func NewHandler(payments paymentCreator) *Handler {
	return &Handler{payments: payments}
}

func (h *Handler) ServeHTTP(writer http.ResponseWriter, request *http.Request) {
	accountID, ok := paymentAccount(request.URL.Path)
	if request.Method != http.MethodPost || !ok {
		http.NotFound(writer, request)
		return
	}

	var input payment.CreateRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&input); err != nil {
		writeError(writer, http.StatusBadRequest, "invalid_request", "request body is invalid")
		return
	}

	created, err := h.payments.Create(request.Context(), accountID, input)
	if errors.Is(err, payment.ErrInvalidRequest) {
		writeError(writer, http.StatusBadRequest, "invalid_request", "payment input is invalid")
		return
	}
	if err != nil {
		writeError(writer, http.StatusInternalServerError, "internal_error", "payment could not be created")
		return
	}

	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(http.StatusCreated)
	_ = json.NewEncoder(writer).Encode(created)
}

func paymentAccount(path string) (string, bool) {
	parts := strings.Split(strings.Trim(path, "/"), "/")
	if len(parts) != 3 || parts[0] != "accounts" || parts[1] == "" || parts[2] != "payments" {
		return "", false
	}
	return parts[1], true
}

func writeError(writer http.ResponseWriter, status int, code, message string) {
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(map[string]string{"code": code, "message": message})
}
