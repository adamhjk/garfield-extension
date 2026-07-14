package main

import (
	"context"
	"flag"
	"fmt"
	"io"
	"os"
	"time"

	"example.com/ledgerlite/internal/invoice"
	"example.com/ledgerlite/internal/store"
)

type invoiceExpirer interface {
	Expire(context.Context, time.Time) ([]invoice.Invoice, error)
}

func run(args []string, stdout, stderr io.Writer, expirer invoiceExpirer) int {
	if len(args) < 2 || args[0] != "invoices" || args[1] != "expire" {
		fmt.Fprintln(stderr, "usage: ledgerctl invoices expire --before RFC3339")
		return 2
	}

	flags := flag.NewFlagSet("invoices expire", flag.ContinueOnError)
	flags.SetOutput(stderr)
	beforeValue := flags.String("before", "", "expire invoices due before this RFC3339 timestamp")
	if err := flags.Parse(args[2:]); err != nil {
		return 2
	}
	before, err := time.Parse(time.RFC3339, *beforeValue)
	if err != nil {
		fmt.Fprintln(stderr, "--before must be an RFC3339 timestamp")
		return 2
	}

	expired, err := expirer.Expire(context.Background(), before)
	if err != nil {
		fmt.Fprintf(stderr, "expire invoices: %v\n", err)
		return 1
	}
	fmt.Fprintf(stdout, "expired %d %s\n", len(expired), invoiceNoun(len(expired)))
	return 0
}

func invoiceNoun(count int) string {
	if count == 1 {
		return "invoice"
	}
	return "invoices"
}

func main() {
	repository := store.NewMemory()
	service := invoice.NewService(repository, time.Now)
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr, service))
}
