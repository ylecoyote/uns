"""Regressions from actual container/browser smoke, not only in-process routing."""

from datetime import UTC
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from tests.uns.api.test_read_models import (
    create_test_ack_audit_record,
    create_test_audit_record,
)

from db.audit_store import SQLAlchemyAuditStore
from db.models import Base
from notification.audit import InMemoryAuditStore
from notification.models import AutonomyMode
from uns.api.read_models import (
    AuditEventFilter,
    DeliveryFilter,
    InMemoryReadModelAdapter,
    SQLAlchemyReadModelAdapter,
)


@pytest.fixture(params=["memory", "sqlite"])
def projection(request, tmp_path):
    if request.param == "memory":
        store = InMemoryAuditStore()
        adapter = InMemoryReadModelAdapter(store)
    else:
        engine = create_engine(f"sqlite:///{tmp_path}/projection.db")
        Base.metadata.create_all(engine)
        sessions = sessionmaker(engine)
        store = SQLAlchemyAuditStore(sessions)
        adapter = SQLAlchemyReadModelAdapter(sessions)
    delivery = create_test_audit_record(
        notification_type="live.smoke", autonomy_mode="LIVE", correlation_id="correlation-smoke"
    )
    store.save_delivery_audit(delivery)
    store.save_ack_audit(create_test_ack_audit_record(notification_id=delivery.notification_id))
    return adapter, delivery


def test_ack_events_preserve_notification_context(projection):
    adapter, delivery = projection
    rows = adapter.get_audit_events(AuditEventFilter(event_type="ack.received")).items
    assert len(rows) == 1
    row = rows[0]
    assert row.autonomy_mode == AutonomyMode.LIVE
    assert row.agent_id == delivery.agent_id
    assert row.notification_type == "live.smoke"
    assert row.correlation_id == "correlation-smoke"


@pytest.mark.parametrize(
    "filters",
    [
        {"agent_id": uuid4()},
        {"autonomy_mode": AutonomyMode.PREVIEW},
        {"correlation_id": "different"},
    ],
)
def test_ack_context_filters_exclude_unrelated_events(projection, filters):
    adapter, _ = projection
    assert (
        adapter.get_audit_events(AuditEventFilter(event_type="ack.received", **filters)).items == []
    )


def test_database_datetimes_keep_explicit_utc_on_wire(projection):
    adapter, delivery = projection
    for event in adapter.get_audit_events(AuditEventFilter()).items:
        assert event.event_time.utcoffset() == UTC.utcoffset(None)
        if event.event_type == "ack.received":
            assert event.payload["acked_at"].endswith("+00:00")
    for row in adapter.get_deliveries(DeliveryFilter()).items:
        assert row.created_at.utcoffset() == UTC.utcoffset(None)
    timeline = adapter.get_delivery_timeline(delivery.notification_id)
    assert timeline.created_at.utcoffset() == UTC.utcoffset(None)


@pytest.mark.asyncio
async def test_invariant_summary_timestamp_has_explicit_timezone():
    from uns.queries import get_invariants_summary

    result = await get_invariants_summary()
    assert result.last_updated.endswith("+00:00")
