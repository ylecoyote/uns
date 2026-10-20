"""Exact channel membership for multi-channel audit records."""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agsignal.api.read_models import DeliveryFilter, SQLAlchemyReadModelAdapter
from db.audit_store import SQLAlchemyAuditStore
from db.models import Base
from notification.audit import create_audit_record
from notification.models import (
    AutonomyContext,
    AutonomyMode,
    Channel,
    DeliveryStatus,
    Notification,
    NotificationIntent,
    NotificationResult,
)


def test_sqlite_filter_matches_channel_anywhere_in_array():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    store = SQLAlchemyAuditStore(sessions)
    notification = Notification(
        notification_type="review.channels",
        intent=NotificationIntent.OPERATIONAL,
        title="Channel filter",
        message="Local only",
        source="test",
        autonomy_context=AutonomyContext(agent_id=uuid4(), autonomy_mode=AutonomyMode.LIVE),
    )
    result = NotificationResult(
        notification_id=notification.notification_id,
        status=DeliveryStatus.DELIVERED,
        channels_attempted=[Channel.SLACK, Channel.EMAIL],
        channels_succeeded=[Channel.EMAIL],
        channels_failed=[Channel.SLACK],
    )
    store.save_delivery_audit(create_audit_record(notification, result))
    reader = SQLAlchemyReadModelAdapter(sessions)
    assert reader.get_deliveries(DeliveryFilter(channel=Channel.SLACK)).total_count == 1
    assert reader.get_deliveries(DeliveryFilter(channel=Channel.EMAIL)).total_count == 1
    assert reader.get_deliveries(DeliveryFilter(channel=Channel.PAGERDUTY)).total_count == 0


def test_postgresql_membership_compiles_to_jsonb_array_containment():
    from sqlalchemy.dialects import postgresql

    from agsignal.api.read_models import _channel_membership
    from db.models import NotificationAuditRecord

    predicate = _channel_membership(
        NotificationAuditRecord.channels_attempted, Channel.SLACK, "postgresql"
    )
    compiled = predicate.compile(dialect=postgresql.dialect())
    assert "JSONB" in str(compiled) and "@>" in str(compiled)
    assert [Channel.SLACK.value] in compiled.params.values()


def test_unknown_dialect_fails_explicitly_instead_of_substring_matching():
    from agsignal.api.read_models import _channel_membership
    from db.models import NotificationAuditRecord

    with pytest.raises(ValueError, match="not implemented"):
        _channel_membership(NotificationAuditRecord.channels_attempted, Channel.SLACK, "unknown")
