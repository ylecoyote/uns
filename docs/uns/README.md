# Historical UNS Extraction Materials

This folder is intentionally preserved as provenance for the AGSignal migration.
In current public product terminology:

| Historical term | Current term |
|-----------------|--------------|
| UNS | AGSignal Core |
| Unified Notification Service | AGSignal Core |
| UNS Dashboard | AGSignal Console |

These documents should not be treated as the public product entrypoint. Start
with the root [AGSignal README](../../README.md) and the main
[AGSignal Documentation](../README.md) for current terminology and product
boundaries.

## Taxonomy Decision

Decision for MIP-242: keep `docs/uns/` as historical extraction material instead
of moving it to `docs/ags/`.

Rationale:

- The folder contains source PRDs, functional specs, technical specs, comms
  drafts, and build-task notes that are useful as migration evidence.
- Moving the folder would make historical references harder to trace.
- Public product docs now lead with AGSignal and AGSignal Core, while this folder
  is explicitly labeled as provenance.

## Current Product Boundary

AGSignal Core owns signal routing, delivery, acknowledgments, policy evaluation,
deduplication, rate limiting, audit records, delivery health, and governance
feedback.

AGSignal Core does not execute actions, block execution loops, replace delivery
tools, or own agent reasoning.

## File Index

| File | Historical role |
|------|-----------------|
| [executive-summary.md](executive-summary.md) | Early product framing and category narrative |
| [one-pager-diagram.md](one-pager-diagram.md) | Shareable system map |
| [unified-notification-service-func-spec.md](unified-notification-service-func-spec.md) | Functional specification |
| [unified-notification-service-tech-spec.md](unified-notification-service-tech-spec.md) | Technical specification |
| [unified_notification_and_signaling_prd.md](unified_notification_and_signaling_prd.md) | PRD source material |
| [uns-comms.md](uns-comms.md) | Feedback/comms draft |
| [uns_ralphy_task_list.md](uns_ralphy_task_list.md) | Historical build-task breakdown |
| [walking-deck.md](walking-deck.md) | Narrative deck outline |
