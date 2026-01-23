# UI Scope – v1

## Design Philosophy

The UNS UI is a **read-first "flight instruments" dashboard**, not a control cockpit. It provides visibility into the notification system's state and health without offering direct manipulation capabilities in the initial release.

## v1 Constraints

| Capability | v1 Status |
|------------|-----------|
| Notification authoring | **Not included** |
| Policy editing | **Not included** |
| Read-only dashboards | Included |
| Metrics & health monitoring | Included |

## Invariant Integrity

**The UI must not bypass system invariants.**

All business rules, validation logic, and safety constraints enforced by the backend remain authoritative. The UI layer is strictly a presentation concern and does not introduce alternative paths that could circumvent policy enforcement or data integrity checks.

## Rationale

1. **Reduce risk** – Limiting write operations in v1 minimizes the attack surface and prevents accidental misconfiguration.
2. **Faster delivery** – A read-only UI ships sooner and provides immediate operational value.
3. **Foundation first** – Observability tooling establishes trust before control capabilities are added.

Future versions may introduce authoring and policy management features once the read-only foundation is validated.
