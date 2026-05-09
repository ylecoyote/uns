"""AGSignal governance — Decision Engine, Policy DSL, ContextSchema, audit.

Per the v1.0 PRD, this package exposes the runtime HITL Approval Control
Plane primitives. v0.4 ships the Decision Engine + supporting types; v0.5
adds the Approval Workflow that consumes REQUIRE_APPROVAL outcomes.

Public surface re-exported here is the stable API for plugins and consumers
(per the Plugin Extension API Surface ADR's `agsignal.contracts` boundary).
"""
