"""YAML policy loader + load-time validation.

Per PRD M3.1: Policy YAML MUST be parsed deterministically; two identical YAMLs
MUST produce identical policy_config_hash.

Per PRD M1.5 / M3.4: at load time we validate (a) operators are in the closed
allowlist, (b) regex patterns fit the length cap (defense in depth), (c) field
references will be checked against the registered ContextSchema (in
context_schema.py / decision_engine.py — load-time field-ref validation lives
where the schema is registered, not here).

This module raises PolicyLoadError for any structural / operator / regex
problem; callers catch and apply hot-reload last-known-good per ADR Fail-mode
Semantics.
"""

from __future__ import annotations

import hashlib
from typing import Any

import yaml
from pydantic import ValidationError

from agsignal.governance.errors import PolicyLoadError
from agsignal.governance.operators import (
    REGEX_PATTERN_LENGTH_CAP,
    parse_operator,
)
from agsignal.governance.policy_dsl import Policy


def load_policy_from_yaml(yaml_text: str) -> Policy:
    """Parse a YAML policy string into a Policy with full load-time validation."""
    try:
        parsed = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        raise PolicyLoadError(f"Invalid YAML syntax: {e}") from e

    if not isinstance(parsed, dict):
        raise PolicyLoadError(f"Policy YAML must be a mapping at the top level, got {type(parsed).__name__}")

    # Pre-validate operators before Pydantic so we can raise PolicyLoadError
    # (rather than ValidationError) for the operator-not-in-allowlist case
    _validate_operators_recursive(parsed)
    _validate_regex_patterns_recursive(parsed)

    try:
        policy = Policy.model_validate(parsed)
    except ValidationError as e:
        raise PolicyLoadError(f"Policy structural validation failed: {e}") from e

    return policy


def _validate_operators_recursive(node: Any) -> None:
    """Walk the parsed YAML tree; reject unknown operators at load time."""
    if isinstance(node, dict):
        if "operator" in node and isinstance(node["operator"], str):
            parse_operator(node["operator"])  # raises PolicyLoadError on unknown
        for v in node.values():
            _validate_operators_recursive(v)
    elif isinstance(node, list):
        for v in node:
            _validate_operators_recursive(v)


def _validate_regex_patterns_recursive(node: Any) -> None:
    """Walk the parsed YAML tree; reject regex patterns above the length cap.

    Specifically: for any condition whose operator is MATCHES, the `value`
    field is treated as a regex pattern and length-checked. We don't compile
    here (compile happens at evaluate-time per the operators module); this is
    purely defense-in-depth length capping.
    """
    if isinstance(node, dict):
        if node.get("operator") == "MATCHES":
            value = node.get("value")
            if isinstance(value, str) and len(value) > REGEX_PATTERN_LENGTH_CAP:
                raise PolicyLoadError(
                    f"MATCHES regex pattern exceeds {REGEX_PATTERN_LENGTH_CAP}-char cap"
                )
        for v in node.values():
            _validate_regex_patterns_recursive(v)
    elif isinstance(node, list):
        for v in node:
            _validate_regex_patterns_recursive(v)


def compute_policy_config_hash(yaml_text: str) -> str:
    """Compute the deterministic hash of a policy YAML for audit purposes.

    Per PRD M3.1: two identical policies MUST produce identical
    policy_config_hash. We hash the canonical YAML text (after re-serialization
    to canonicalize whitespace and key ordering).
    """
    try:
        parsed = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        raise PolicyLoadError(f"Invalid YAML syntax: {e}") from e

    canonical = yaml.safe_dump(parsed, sort_keys=True, default_flow_style=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
