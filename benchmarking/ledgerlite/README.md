# ledgerlite

`ledgerlite` is a deliberately small invoice and payment service used by the
Garfield coordinator benchmark. It has no network or service dependencies.

## Validation

Run the aggregate validation entry point from the repository root:

```sh
./tools/validate.sh
```

That runs `go test ./...`, `go vet ./...`, and verifies that
`generated/client.go` exactly matches `api/openapi.json`.

Regenerate the client with:

```sh
go run ./tools/generate
```

## Packages

- `internal/invoice` owns invoice expiration behavior.
- `internal/payment` owns payment creation behavior.
- `internal/store` is the deterministic in-memory repository.
- `internal/api` exposes payment creation over HTTP.
- `cmd/ledgerctl` contains the invoice-expiration CLI.
