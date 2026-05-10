"""Operator allowlist + evaluation for the Policy DSL.

Per ADR Decision Engine Internal Shape:
- Closed operator allowlist; operators outside it MUST be rejected at policy load
- MATCHES uses RE2 (no catastrophic backtracking); FULLMATCH semantics (anchored
  at start AND end by default)
- Pathological regex length is capped as defense in depth; the cap is hit at
  policy load when feasible, but enforced at evaluate-time too

This module is the only place operator semantics live. Adding an operator
requires an ADR amendment + major version bump (per PRD M3.2 ReDoS cap +
operator-allowlist closure rules).
"""

from __future__ import annotations

from enum import Enum
from typing import Any

import re2

from agsignal.governance.errors import PolicyEvaluationError, PolicyLoadError

REGEX_PATTERN_LENGTH_CAP = 1024  # characters; ReDoS defense in depth


class Operator(str, Enum):
    """Closed operator allowlist per ADR Decision Engine Internal Shape M3.2."""

    EQ = "EQ"
    NEQ = "NEQ"
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"
    IN = "IN"
    NOT_IN = "NOT_IN"
    EXISTS = "EXISTS"
    NOT_EXISTS = "NOT_EXISTS"
    MATCHES = "MATCHES"


_OPERATOR_NAMES = {op.value for op in Operator}


def parse_operator(name: str) -> Operator:
    """Parse a string operator name; reject unknowns at policy-load time."""
    if name not in _OPERATOR_NAMES:
        raise PolicyLoadError(
            f"Operator {name!r} is not in the allowlist. Allowed: {sorted(_OPERATOR_NAMES)}"
        )
    return Operator(name)


def evaluate_operator(op: Operator, lhs: Any, rhs: Any) -> bool:
    """Evaluate a binary operator against (lhs, rhs).

    For EXISTS / NOT_EXISTS, lhs=None means "missing"; rhs is ignored entirely
    (the YAML loader in Task 5 may omit it or pass null, both work).
    For MATCHES, rhs is the regex pattern (compiled fullmatch).
    """
    try:
        if op == Operator.EQ:
            return lhs == rhs
        if op == Operator.NEQ:
            return lhs != rhs
        if op == Operator.GT:
            _check_orderable(lhs, rhs, op)
            return lhs > rhs
        if op == Operator.GTE:
            _check_orderable(lhs, rhs, op)
            return lhs >= rhs
        if op == Operator.LT:
            _check_orderable(lhs, rhs, op)
            return lhs < rhs
        if op == Operator.LTE:
            _check_orderable(lhs, rhs, op)
            return lhs <= rhs
        if op == Operator.IN:
            _check_iterable(rhs, op)
            return lhs in rhs
        if op == Operator.NOT_IN:
            _check_iterable(rhs, op)
            return lhs not in rhs
        if op == Operator.EXISTS:
            return lhs is not None
        if op == Operator.NOT_EXISTS:
            return lhs is None
        if op == Operator.MATCHES:
            return _evaluate_matches(lhs, rhs)
    except PolicyEvaluationError:
        raise
    except Exception as e:
        raise PolicyEvaluationError(
            message=f"Operator {op.value} raised unexpectedly: {type(e).__name__}: {e}"
        ) from e

    raise PolicyEvaluationError(message=f"Unhandled operator: {op.value}")


def _check_orderable(lhs: Any, rhs: Any, op: Operator) -> None:
    """Type-compatibility check for ordered comparisons (GT, LT, GTE, LTE)."""
    if isinstance(lhs, bool) or isinstance(rhs, bool):
        # bool is int subtype; reject explicitly so 'True > 0' doesn't sneak through
        raise PolicyEvaluationError(
            message=f"Operator {op.value} type mismatch: bool not orderable in policy DSL"
        )
    if type(lhs) is not type(rhs) and not (
        isinstance(lhs, (int, float)) and isinstance(rhs, (int, float))
    ):
        raise PolicyEvaluationError(
            message=f"Operator {op.value} type mismatch: {type(lhs).__name__} vs {type(rhs).__name__}"
        )


def _check_iterable(rhs: Any, op: Operator) -> None:
    """The rhs of IN / NOT_IN must be iterable (list/tuple/set/dict/range/etc.), not a string or bytes.

    Strings and bytes are rejected explicitly because `"a" in "ab"` is a frequent
    YAML-author footgun where they meant `IN ["ab"]`. The `__contains__` fallback
    accepts any container (including dict, where `in` checks keys) — YAML loaders
    typically produce list, so this only matters in programmatic construction.
    """
    if isinstance(rhs, (str, bytes)) or not hasattr(rhs, "__contains__"):
        raise PolicyEvaluationError(
            message=f"Operator {op.value} requires a list/set/tuple on the right-hand side, got {type(rhs).__name__}"
        )


def _evaluate_matches(lhs: Any, pattern: Any) -> bool:
    """Evaluate MATCHES with RE2 (no catastrophic backtracking) and full anchoring."""
    if not isinstance(lhs, str):
        raise PolicyEvaluationError(
            message=f"Operator MATCHES requires a string on the left-hand side, got {type(lhs).__name__}"
        )
    if not isinstance(pattern, str):
        raise PolicyEvaluationError(
            message=f"Operator MATCHES requires a string regex pattern, got {type(pattern).__name__}"
        )
    if len(pattern) > REGEX_PATTERN_LENGTH_CAP:
        raise PolicyEvaluationError(
            message=f"Operator MATCHES regex pattern exceeds {REGEX_PATTERN_LENGTH_CAP}-char cap (defense in depth)"
        )
    try:
        compiled = re2.compile(pattern)
    except re2.error as e:
        raise PolicyEvaluationError(
            message=f"Operator MATCHES regex compile failed: {e}"
        ) from e
    # fullmatch: anchored at start AND end (per ADR RE2 fully-anchored)
    return compiled.fullmatch(lhs) is not None
