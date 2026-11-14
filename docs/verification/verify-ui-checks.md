# Verification checks for the UI layer

Repository-specific checks for the global `/verify` and `/verify_invariants`
commands. They apply when `/verify` runs with `--ui-boundary` or `--contracts`,
and when `/verify_invariants` covers UI scope. They lived in the global command
files until 2026-11-13 and moved here because they apply only to this repository.

Examples:

- `/verify docs/ui/ui-data-contracts.md apps/ui/src/types/ --contracts`: UI contract alignment
- `/verify apps/ui/ --ui-boundary --bounded`: UI architectural boundaries
- `/verify docs/ui/ui-scope.md apps/ui/ --docs-code --ui-boundary`: UI scope compliance
- `/verify_invariants --focus INV-UI-001`: the read-only UI invariant

## UI boundary checks (`--ui-boundary`)

### Architectural constraints

1. **No Python in canonical UI paths:** `apps/ui/**` (excluding `legacy_flask_reference/`) contains no Python artifacts.
2. **No templates or Flask runtime:** the canonical UI is a React SPA only; no server-rendered templates.
3. **No direct backend imports:** UI code does not import from `src/notification/` or other Python modules.
4. **Read-only endpoints only:** the UI consumes only GET endpoints under `/ui/*` or `/api/v1/*`.
5. **No mutation actions:** no POST/PUT/DELETE exposed in UI Phase 1.

### INV-UI-001: read-only UI

From [invariants.yml](invariants.yml):

> UI endpoints must be read-only. The UI layer is strictly a presentation concern and does not introduce write operations.

Enforcement evidence to seek:

- All UI endpoint handlers use the `@router.get()` decorator.
- POST/PUT/PATCH/DELETE return 405 Method Not Allowed.
- Read-model adapters implement only read (`get_*`) operations.

### Related documentation

- [UI Scope v1](../ui/ui-scope.md): authoritative scope definition
- `apps/ui/README.md`: design principles and constraints
- `docs/reports/ui/`: bounded phase verification reports

## Contract checks (`--contracts`)

### Contract alignment

1. **Backend response shapes** match [UI Data Contracts](../ui/ui-data-contracts.md).
2. **TypeScript type definitions** in `apps/ui/src/types/` match the documented contracts.
3. **API client decoders** in `apps/ui/src/api/` handle every documented response field.
4. **Pagination semantics:** cursor-based pagination matches the contract specification.
5. **Error response structure:** error codes and shapes match the `ErrorResponse` contract.

### Contract drift indicators

- **Missing fields:** the backend returns fields absent from the TypeScript types.
- **Type mismatches:** number vs string, optional vs required.
- **Enum drift:** status or intent values that differ between backend and frontend.
- **Pagination inconsistency:** cursor or limit behavior that differs from the documentation.

### Evidence sources

- Contract tests in `tests/` directories
- TypeScript type definitions in `apps/ui/src/types/`
- API client implementations in `apps/ui/src/api/`
- OpenAPI or schema definitions, if present
