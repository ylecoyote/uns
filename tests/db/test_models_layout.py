"""Verify db.models package re-exports keep historical import paths working."""

from __future__ import annotations


def test_db_models_reexports_all_public_classes() -> None:
    from db import models

    expected = {
        "Base",
        "DeliveryStatusDB",
        "AckStatusDB",
        "NotificationAuditRecord",
        "AckAuditRecord",
        "PersistedNotificationPolicy",
        "WebSocketReplayRecord",
        "PersistedPolicyDelta",
        "PersistedShadowEvaluationResult",
        "PersistedShadowEvaluationAggregate",
    }
    actual = set(models.__all__)
    missing = expected - actual
    assert not missing, f"Missing re-exports: {missing}"


def test_each_persisted_class_lives_in_its_focused_module() -> None:
    """Audit, policy, learning, websocket each have their own module."""
    # Round-trip through the package re-exports too.
    from db.models import AckAuditRecord as AckAuditRecord2
    from db.models import NotificationAuditRecord as NotificationAuditRecord2
    from db.models import PersistedNotificationPolicy as PersistedNotificationPolicy2
    from db.models import PersistedPolicyDelta as PersistedPolicyDelta2
    from db.models import (
        PersistedShadowEvaluationAggregate as PersistedShadowEvaluationAggregate2,
    )
    from db.models import PersistedShadowEvaluationResult as PersistedShadowEvaluationResult2
    from db.models import WebSocketReplayRecord as WebSocketReplayRecord2
    from db.models.audit import AckAuditRecord, NotificationAuditRecord
    from db.models.policy import PersistedNotificationPolicy
    from db.models.policy_learning import (
        PersistedPolicyDelta,
        PersistedShadowEvaluationAggregate,
        PersistedShadowEvaluationResult,
    )
    from db.models.websocket import WebSocketReplayRecord

    assert AckAuditRecord is AckAuditRecord2
    assert NotificationAuditRecord is NotificationAuditRecord2
    assert PersistedNotificationPolicy is PersistedNotificationPolicy2
    assert PersistedPolicyDelta is PersistedPolicyDelta2
    assert PersistedShadowEvaluationAggregate is PersistedShadowEvaluationAggregate2
    assert PersistedShadowEvaluationResult is PersistedShadowEvaluationResult2
    assert WebSocketReplayRecord is WebSocketReplayRecord2
