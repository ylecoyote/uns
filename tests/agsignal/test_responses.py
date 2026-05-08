"""Smoke contract tests for relocated Pydantic DTOs.

These tests guard against signature drift introduced during the Phase 3
relocation. The route-level behavioral tests
(``tests/notification/test_*.py``, ``tests/mcp_server/test_routes_*.py``)
are the primary regression cover; these tests just confirm round-trip
serialization is intact for one representative class per family.
"""

from __future__ import annotations

import pytest

from agsignal.responses import (
    AckRequest,
    AuditEventType,
    AutonomyContextRequest,
    DeliveryAttempt,
    DeliveryTimelineResponse,
    NotificationErrorResponse,
    SendNotificationRequest,
    UIErrorResponse,
)
from notification.models import NotificationIntent


def test_send_notification_request_round_trip() -> None:
    """Notification write Request — confirms field set + extra='forbid'."""
    payload = {
        "notification_type": "test.signal",
        "intent": "INFORMATIONAL",
        "title": "test",
        "message": "test",
        "source": "test-suite",
        "autonomy_context": {
            "agent_id": "00000000-0000-0000-0000-000000000001",
            "autonomy_mode": "PREVIEW",
        },
    }
    request = SendNotificationRequest.model_validate(payload)
    assert request.notification_type == "test.signal"
    assert request.intent == NotificationIntent.INFORMATIONAL
    serialized = request.model_dump(mode="json")
    SendNotificationRequest.model_validate(serialized)


def test_send_notification_request_forbids_extras() -> None:
    """SendNotificationRequest has model_config = ConfigDict(extra='forbid')."""
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        SendNotificationRequest.model_validate(
            {
                "notification_type": "x",
                "intent": "INFORMATIONAL",
                "title": "t",
                "message": "m",
                "source": "s",
                "autonomy_context": {
                    "agent_id": "00000000-0000-0000-0000-000000000001",
                    "autonomy_mode": "PREVIEW",
                },
                "unknown_field": True,
            }
        )


def test_autonomy_context_request_to_domain_method_preserved() -> None:
    """AutonomyContextRequest has a to_domain() method that constructs
    AutonomyContext. The verbatim copy must include the method."""
    request = AutonomyContextRequest.model_validate(
        {
            "agent_id": "00000000-0000-0000-0000-000000000001",
            "autonomy_mode": "PREVIEW",
        }
    )
    domain = request.to_domain()
    assert hasattr(domain, "agent_id")
    assert str(domain.agent_id) == "00000000-0000-0000-0000-000000000001"


def test_ack_request_round_trip() -> None:
    """Acknowledgment family — Request shape."""
    request = AckRequest.model_validate({"acked_by": "operator", "metadata": {}})
    serialized = request.model_dump(mode="json")
    AckRequest.model_validate(serialized)


def test_delivery_timeline_response_with_nested_attempt() -> None:
    """Console / read family — composite Response with sub-DTO."""
    attempt = DeliveryAttempt.model_validate(
        {
            "attempt_id": "00000000-0000-0000-0000-000000000010",
            "channel": "SLACK",
            "status": "SUCCESS",
            "started_at": "2026-05-08T00:00:00Z",
            "completed_at": "2026-05-08T00:00:01Z",
            "duration_ms": 1000,
        }
    )
    timeline = DeliveryTimelineResponse.model_validate(
        {
            "notification_id": "00000000-0000-0000-0000-000000000001",
            "notification_type": "test",
            "intent": "INFORMATIONAL",
            "delivery_mode": "BEST_EFFORT",
            "status": "SUCCESS",
            "created_at": "2026-05-08T00:00:00Z",
            "attempts": [attempt.model_dump(mode="json")],
            "channels_attempted": ["SLACK"],
            "channels_succeeded": ["SLACK"],
            "channels_failed": [],
            "autonomy_context": {
                "autonomy_mode": "PREVIEW",
                "agent_id": "00000000-0000-0000-0000-000000000002",
            },
        }
    )
    assert len(timeline.attempts) == 1
    serialized = timeline.model_dump(mode="json")
    DeliveryTimelineResponse.model_validate(serialized)


def test_audit_event_type_enum_values() -> None:
    """Enums survive relocation with same string values."""
    assert isinstance(AuditEventType("notification.created"), AuditEventType)
    assert AuditEventType.DELIVERY_FAILED.value == "delivery.failed"


def test_notification_error_response_disambiguated_from_ui() -> None:
    """NotificationErrorResponse and UIErrorResponse are structurally different.
    The relocation deliberately renamed the two ErrorResponse classes."""
    notif_error = NotificationErrorResponse.model_validate(
        {
            "error": "validation_error",
            "message": "Invalid input",
            "notification_id": None,
        }
    )
    assert notif_error.error == "validation_error"
    # UIErrorResponse uses ErrorDetail, not bare strings
    ui_error = UIErrorResponse.model_validate(
        {
            "error": {"code": "not_found", "message": "Not found", "details": None},
            "request_id": "req-123",
        }
    )
    assert ui_error.request_id == "req-123"
