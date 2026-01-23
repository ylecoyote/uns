"""Audit Timeline page.

This module provides the audit event timeline functionality
for browsing the audit trail of notification-related events.

Routes:
    GET /audit - List audit events with filtering

Filters available:
    - event_type: Filter by event type
    - notification_id: Filter by notification UUID
    - agent_id: Filter by agent UUID
    - autonomy_mode: Filter by PREVIEW, SHADOW, or LIVE
    - correlation_id: Filter by correlation ID
    - time_range: start_time, end_time

Event Types:
    - notification.created
    - delivery.started, delivery.succeeded, delivery.failed
    - delivery.deduplicated, delivery.rate_limited
    - delivery.channel_attempted
    - ack.pending, ack.received, ack.dismissed, ack.timed_out
    - escalation.triggered
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuditPageState:
    """State for the Audit Timeline page.

    Attributes:
        cursor: Current pagination cursor.
        filters: Active filter values.
        loading: Whether data is being fetched.
        error: Error message if any.
    """

    cursor: str | None = None
    filters: dict[str, str] | None = None
    loading: bool = False
    error: str | None = None


# Page placeholders - actual implementation in Phase 1 task 6


def get_audit_page_title() -> str:
    """Get the page title for the Audit Timeline."""
    return "Audit Timeline"


def get_available_filters() -> tuple[str, ...]:
    """Return the available filter keys for the Audit page."""
    return (
        "event_type",
        "notification_id",
        "agent_id",
        "autonomy_mode",
        "correlation_id",
        "start_time",
        "end_time",
    )


def get_event_type_options() -> tuple[str, ...]:
    """Return the available event type options."""
    return (
        "notification.created",
        "delivery.started",
        "delivery.channel_attempted",
        "delivery.succeeded",
        "delivery.failed",
        "delivery.deduplicated",
        "delivery.rate_limited",
        "ack.pending",
        "ack.received",
        "ack.dismissed",
        "ack.timed_out",
        "escalation.triggered",
    )


def get_autonomy_mode_options() -> tuple[str, ...]:
    """Return the available autonomy mode options."""
    return ("PREVIEW", "SHADOW", "LIVE")
