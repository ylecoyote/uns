"""Policy DSL Pydantic models — Policy, Rule, Condition, ThenClause.

Per ADR Decision Engine Internal Shape:
- Multiple `when` conditions are AND-joined (implicit AND)
- `when` MUST have at least one condition
- Rules within a policy MUST have unique `id`s
- `priority` is optional; rules iterate in source order with optional priority override
- `default_decision` is optional; absent means "deny-by-default no-match"

The DSL is intentionally minimal. Boolean OR within a single rule is expressed
by writing two rules with overlapping `when` clauses; not adding `or:` syntax
in v0.4 (would require ADR amendment).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agsignal.governance.decision_record import Decision
from agsignal.governance.operators import Operator


class Condition(BaseModel):
    """A single field-operator-value predicate."""

    model_config = ConfigDict(extra="forbid")

    field: str = Field(..., description="Dot-notation path into the context capsule (e.g., 'order.notional_usd')")
    operator: Operator
    value: Any = Field(default=None, description="Right-hand side value; type depends on operator")


class ThenClause(BaseModel):
    """The action and (optional) reason for a matched rule."""

    model_config = ConfigDict(extra="forbid")

    decision: Decision
    reason: str | None = None
    target_reviewer_role: str | None = Field(
        None, description="When decision is REQUIRE_APPROVAL, the role responsible for ACK"
    )


class Rule(BaseModel):
    """A `when` predicate (AND-joined conditions) + `then` outcome."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Stable rule identifier; unique within a Policy")
    when: list[Condition] = Field(..., min_length=1, description="AND-joined conditions; at least one required")
    then: ThenClause
    priority: int | None = Field(
        None,
        description="Optional integer priority; lower values evaluated first when present. Source order is the default.",
    )


class Policy(BaseModel):
    """A complete governance policy bundle."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Human-readable policy identifier")
    version: str = Field(..., description="Semantic version of the policy")
    context_schema: str = Field(..., description="Name of the registered ContextSchema this policy operates on")
    rules: list[Rule] = Field(default_factory=list)
    default_decision: Decision | None = Field(
        None,
        description="Outcome when no rule matches. None means deny-by-default per ADR.",
    )

    @field_validator("rules")
    @classmethod
    def rules_must_have_unique_ids(cls, v: list[Rule]) -> list[Rule]:
        ids = [r.id for r in v]
        if len(ids) != len(set(ids)):
            duplicates = [i for i in ids if ids.count(i) > 1]
            raise ValueError(f"Rule ids must be unique; duplicates: {sorted(set(duplicates))}")
        return v
