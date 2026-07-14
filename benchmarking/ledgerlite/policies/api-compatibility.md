# API compatibility

Public HTTP status codes and JSON error objects are contracts. Error responses
use `{"code":"...","message":"..."}`. Update `api/openapi.json`, handler
tests, and the generated client together when the contract changes.
