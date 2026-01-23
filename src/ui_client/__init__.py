"""Typed UI API Client for the Unified Notification Service.

This package provides a strongly-typed Python client for interacting with
the UNS UI API endpoints (/ui/*). It mirrors the response types from
the routes_ui.py module and provides convenient methods for all endpoints.

Features:
- Full type safety with Pydantic models
- Automatic pagination handling
- Error handling with typed exceptions
- Support for all UI endpoint filters
- Request ID propagation for correlation

Example:
    >>> from ui_client import UIApiClient, DeliveryFilters
    >>> client = UIApiClient(base_url="http://localhost:8000")
    >>> deliveries = client.list_deliveries(
    ...     filters=DeliveryFilters(status=DeliveryStatus.DELIVERED)
    ... )
    >>> for delivery in deliveries.items:
    ...     print(f"{delivery.notification_id}: {delivery.status}")
"""

from ui_client.client import (
    UIApiClient,
    create_ui_client,
)
from ui_client.errors import (
    InvalidCursorError,
    InvalidParameterError,
    NotFoundError,
    RateLimitedError,
    UIApiError,
    UIApiServerError,
)
from ui_client.filters import (
    AuditFilters,
    DeliveryFilters,
    InvariantFilters,
)
from ui_client.types import (
    AuditEvent,
    AuditEventListResponse,
    AuditEventType,
    AutonomyContextResponse,
    DeliveryAttempt,
    DeliveryTimelineListResponse,
    DeliveryTimelineResponse,
    DeliveryTimelineSummary,
    EffectivePolicyResponse,
    EffectivePolicyValues,
    EnforcementType,
    ErrorDetail,
    ErrorResponse,
    EvidenceLink,
    InvariantEnforcement,
    InvariantEntry,
    InvariantListResponse,
    InvariantSeverity,
    InvariantStatus,
    InvariantSummaryResponse,
    PaginationInfo,
    ResolutionContext,
    ResolutionSource,
    ResolutionStep,
)

__all__ = [
    # Client
    "UIApiClient",
    "create_ui_client",
    # Errors
    "UIApiError",
    "NotFoundError",
    "InvalidParameterError",
    "InvalidCursorError",
    "RateLimitedError",
    "UIApiServerError",
    # Filters
    "DeliveryFilters",
    "AuditFilters",
    "InvariantFilters",
    # Types - Common
    "PaginationInfo",
    "ErrorDetail",
    "ErrorResponse",
    # Types - Delivery
    "DeliveryAttempt",
    "AutonomyContextResponse",
    "DeliveryTimelineResponse",
    "DeliveryTimelineSummary",
    "DeliveryTimelineListResponse",
    # Types - Policy
    "ResolutionSource",
    "ResolutionStep",
    "EffectivePolicyValues",
    "ResolutionContext",
    "EffectivePolicyResponse",
    # Types - Invariant
    "EnforcementType",
    "InvariantSeverity",
    "InvariantStatus",
    "EvidenceLink",
    "InvariantEnforcement",
    "InvariantEntry",
    "InvariantListResponse",
    "InvariantSummaryResponse",
    # Types - Audit
    "AuditEventType",
    "AuditEvent",
    "AuditEventListResponse",
]
