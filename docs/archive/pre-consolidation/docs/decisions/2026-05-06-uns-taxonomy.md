> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# UNS Taxonomy

## Status

Accepted.

## Context

UNS was extracted from earlier Unified Notification Service (UNS) planning
and build materials. The repository now presents UNS as the product and
UNS Core as the runtime. The `docs/uns/` folder still contains source PRDs,
functional specs, technical specs, comms drafts, and build-task notes that are
useful for provenance.

The migration project needed a durable taxonomy decision for whether to keep
`docs/uns/`, move it to `docs/ags/`, or split product-facing and runtime-facing
docs into new folders.

## Decision

Keep `docs/uns/` as historical extraction material.

Do not move the folder to `docs/ags/`. Do not treat `docs/uns/` as the public
product documentation entrypoint. Current product documentation starts at the
root `README.md`, `docs/README.md`, `docs/API.md`, and `docs/ARCHITECTURE.md`.

## Terminology Mapping

| Historical term | Current term |
|-----------------|--------------|
| UNS | UNS Core |
| Unified Notification Service | UNS Core |
| UNS Dashboard | UNS Console |

## Rationale

- Keeping `docs/uns/` preserves historical references and source material.
- Moving the folder would make prior extraction notes harder to trace.
- UNS is unreleased, so a public migration guide would imply a shipped
  audience and backward-compatibility obligation that does not exist yet.
- The public docs already lead with UNS terminology, while `docs/uns/`
  is explicitly labeled as provenance.

## Consequences

- New public-facing docs should use UNS, AGS, UNS Core, and UNS
  Console terminology.
- UNS language is acceptable inside `docs/uns/`, historical reports, tests that
  protect compatibility, and runtime compatibility notes.
- If a future release ships with UNS terminology, revisit this decision before
  publishing external migration guidance.
