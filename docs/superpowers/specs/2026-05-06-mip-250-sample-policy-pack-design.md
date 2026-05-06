# MIP-250 Sample Policy Pack Design

Date: 2026-05-06

Status: Approved

Linear: [MIP-250](https://linear.app/awiley-personal/issue/MIP-250/publish-mip-uns-policies-as-agsignal-sample-policy-set)

## Goal

Publish the MIP-derived UNS notification policies as a clearly labeled AGSignal
sample policy pack that downstream applications can study, copy, and adapt
without making MIP trading semantics part of AGSignal Core.

## Context

The AGSignal repository already carries three MIP-flavored notification policies
under `config/notification_policies/`:

- `safety.kill_switch`
- `governance.approval_required`
- `execution.slippage`

Those files are loadable by the current AGSignal YAML policy loader, but their
role is ambiguous: they are both realistic donor examples and the current
standalone runtime default path. M5 needs a publishable product story where MIP
policy content is useful as sample material but not presented as default product
behavior.

## Design

Create a dedicated sample pack under `examples/policies/mip-uns/`.

The sample pack will duplicate the current MIP-derived YAML policies and include
a README that explains:

- the files are examples derived from the Market Insights Platform UNS donor;
- the files are not required defaults for AGSignal Core;
- each policy demonstrates a specific AGSignal capability;
- downstream applications should copy and adapt them to their own domain;
- MIP/ATP-specific semantics stay outside AGSignal Core.

The existing `config/notification_policies/` directory will remain unchanged in
this issue. Moving or narrowing runtime defaults would change current standalone
route behavior and belongs in a later configuration-boundary issue if needed.

## Sample Pack Contents

| Policy | Demonstrates |
|---|---|
| `safety_kill_switch.yaml` | LIVE-mode guaranteed delivery, PagerDuty escalation, required ACK |
| `governance_approval_required.yaml` | Approval workflow routing and failure escalation |
| `execution_slippage.yaml` | Best-effort operational signaling and deduplication window |

## Documentation Updates

The sample pack will be linked from:

- `docs/README.md`
- `docs/m5-publish-readiness-reference.md`
- a dedicated sample pack README under `examples/policies/mip-uns/`

The docs must keep the distinction between shipped behavior, sample behavior,
and planned M5 parity work.

## Tests

Add tests that prove:

- the sample policy directory exists;
- all sample policies load through `load_policies_from_directory()`;
- representative routing and acknowledgment behavior matches the README claims;
- the docs index references the sample policy pack.

## Non-Goals

- Do not port the full MIP policy learning engine.
- Do not move runtime defaults out of `config/notification_policies/`.
- Do not introduce MIP or ATP imports into AGSignal Core.
- Do not make trading-domain policy names mandatory for AGSignal users.

## Acceptance Criteria

- `examples/policies/mip-uns/` contains the three MIP-derived sample policies.
- The sample README explains what is generic AGSignal behavior and what is
  MIP-specific sample content.
- Tests prove the sample pack loads and routes as documented.
- Public docs link to the sample pack without implying it is default behavior.

