# Ledgerlite agent instructions

Keep changes confined to the requested implementation slice and preserve
existing CLI and API behavior unless the prompt explicitly changes it.

## Required validation

Run `./tools/validate.sh` after implementation changes. The command must finish
without network access. Do not hand-edit `generated/client.go`; update
`api/openapi.json`, run `go run ./tools/generate`, and commit both artifacts.

## Repository skills

Load only skills relevant to the current slice:

- `.agents/skills/repository-testing/SKILL.md`
- `.agents/skills/api-contract-review/SKILL.md`
- `.agents/skills/storage-invariants/SKILL.md`
- `.agents/skills/generated-artifacts/SKILL.md`

Policies under `policies/` are authoritative for their named scope.
