"""Tests for the YAML policy loader."""

from textwrap import dedent

import pytest

from uns.governance.decision_record import Decision
from uns.governance.errors import PolicyLoadError
from uns.governance.operators import Operator
from uns.governance.policy_loader import (
    compute_policy_config_hash,
    load_policy_from_yaml,
)


def test_loads_minimal_policy():
    yaml_text = dedent(
        """
        id: trade-approval
        version: "1.0"
        context_schema: trading
        rules:
          - id: high_notional
            when:
              - field: notional_usd
                operator: GT
                value: 1000000
            then:
              decision: REQUIRE_APPROVAL
              reason: "Notional exceeds $1M"
        """
    ).strip()
    p = load_policy_from_yaml(yaml_text)
    assert p.id == "trade-approval"
    assert p.context_schema == "trading"
    assert len(p.rules) == 1
    assert p.rules[0].when[0].operator == Operator.GT
    assert p.rules[0].then.decision == Decision.REQUIRE_APPROVAL


def test_rejects_unknown_operator_at_load():
    yaml_text = dedent(
        """
        id: bad
        version: "1.0"
        context_schema: trading
        rules:
          - id: r1
            when:
              - field: x
                operator: CONTAINS  # not in allowlist
                value: 1
            then:
              decision: ALLOW
        """
    ).strip()
    with pytest.raises(PolicyLoadError) as exc:
        load_policy_from_yaml(yaml_text)
    assert "CONTAINS" in str(exc.value)


def test_rejects_invalid_yaml_syntax():
    yaml_text = "id: [this is invalid"
    with pytest.raises(PolicyLoadError):
        load_policy_from_yaml(yaml_text)


def test_rejects_missing_required_field():
    yaml_text = dedent(
        """
        id: missing_version
        context_schema: trading
        rules: []
        """
    ).strip()
    with pytest.raises(PolicyLoadError) as exc:
        load_policy_from_yaml(yaml_text)
    assert "version" in str(exc.value).lower()


def test_compute_policy_config_hash_deterministic():
    yaml_a = dedent(
        """
        id: p
        version: "1.0"
        context_schema: trading
        rules:
          - id: r1
            when: [{field: x, operator: EQ, value: 1}]
            then: {decision: ALLOW}
        """
    ).strip()
    yaml_b = yaml_a  # exact same content
    h_a = compute_policy_config_hash(yaml_a)
    h_b = compute_policy_config_hash(yaml_b)
    assert h_a == h_b
    assert h_a.startswith("sha256:")


def test_compute_policy_config_hash_changes_with_content():
    yaml_a = dedent(
        """
        id: p
        version: "1.0"
        context_schema: trading
        rules:
          - id: r1
            when: [{field: x, operator: EQ, value: 1}]
            then: {decision: ALLOW}
        """
    ).strip()
    yaml_b = yaml_a.replace("ALLOW", "DENY")
    assert compute_policy_config_hash(yaml_a) != compute_policy_config_hash(yaml_b)


def test_pathological_regex_caught_at_load():
    long_pattern = "a" * 2000  # exceeds REGEX_PATTERN_LENGTH_CAP
    yaml_text = dedent(
        f"""
        id: bad_regex
        version: "1.0"
        context_schema: trading
        rules:
          - id: r1
            when:
              - field: action
                operator: MATCHES
                value: "{long_pattern}"
            then:
              decision: DENY
        """
    ).strip()
    with pytest.raises(PolicyLoadError) as exc:
        load_policy_from_yaml(yaml_text)
    assert "regex" in str(exc.value).lower() or "cap" in str(exc.value).lower()
