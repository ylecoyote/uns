#!/usr/bin/env python3
"""Generate a machine-readable contract snapshot for /ui endpoints.

This script extracts JSON schemas from the Pydantic models in
``uns.responses`` and generates a deterministic contract snapshot
file at:
    docs/ui/contracts/ui-contracts.json

The snapshot includes:
- All response schemas for /ui endpoints
- Enum definitions with allowed values
- Endpoint metadata (method, path, description)
- Generated timestamp and version

Usage:
    python scripts/generate_ui_contracts.py

Output:
    docs/ui/contracts/ui-contracts.json

The output is deterministically sorted to ensure stable diffs when contracts change.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


def get_enum_definitions() -> dict[str, list[str]]:
    """Extract enum definitions from notification.models and uns.responses."""
    from notification.models import (
        AckStatus,
        AutonomyMode,
        Channel,
        DeliveryMode,
        DeliveryStatus,
        NotificationIntent,
        Priority,
    )
    from uns.responses import (
        AuditEventType,
        EnforcementType,
        InvariantSeverity,
        InvariantStatus,
        ResolutionSource,
    )

    enums = {
        "NotificationIntent": [e.value for e in NotificationIntent],
        "DeliveryMode": [e.value for e in DeliveryMode],
        "AutonomyMode": [e.value for e in AutonomyMode],
        "Channel": [e.value for e in Channel],
        "DeliveryStatus": [e.value for e in DeliveryStatus],
        "AckStatus": [e.value for e in AckStatus],
        "Priority": [e.value for e in Priority],
        "AuditEventType": [e.value for e in AuditEventType],
        "EnforcementType": [e.value for e in EnforcementType],
        "InvariantSeverity": [e.value for e in InvariantSeverity],
        "InvariantStatus": [e.value for e in InvariantStatus],
        "ResolutionSource": [e.value for e in ResolutionSource],
    }

    # Sort enum values for determinism
    return {k: sorted(v) for k, v in sorted(enums.items())}


def get_response_schemas() -> dict[str, dict[str, Any]]:
    """Extract JSON schemas from Pydantic response models."""
    from uns.responses import (
        AuditEvent,
        AuditEventListResponse,
        AutonomyContextResponse,
        DeliveryAttempt,
        DeliveryTimelineListResponse,
        DeliveryTimelineResponse,
        DeliveryTimelineSummary,
        EffectivePolicyResponse,
        EffectivePolicyValues,
        ErrorDetail,
        EvidenceLink,
        InvariantEnforcement,
        InvariantEntry,
        InvariantListResponse,
        InvariantSummaryResponse,
        PaginationInfo,
        ResolutionContext,
        ResolutionStep,
    )
    from uns.responses import (
        UIErrorResponse as ErrorResponse,
    )

    # List of all response models to include
    models = [
        # Common types
        PaginationInfo,
        ErrorDetail,
        ErrorResponse,
        # Delivery timeline
        DeliveryAttempt,
        AutonomyContextResponse,
        DeliveryTimelineResponse,
        DeliveryTimelineSummary,
        DeliveryTimelineListResponse,
        # Policy resolution
        ResolutionStep,
        EffectivePolicyValues,
        ResolutionContext,
        EffectivePolicyResponse,
        # Invariants
        EvidenceLink,
        InvariantEnforcement,
        InvariantEntry,
        InvariantListResponse,
        InvariantSummaryResponse,
        # Audit events
        AuditEvent,
        AuditEventListResponse,
    ]

    schemas = {}
    for model in models:
        # Get JSON schema from Pydantic model
        schema = model.model_json_schema()
        # Remove $defs if present (definitions are inlined or handled separately)
        # Keep the core schema clean
        schemas[model.__name__] = schema

    # Sort for determinism
    return dict(sorted(schemas.items()))


def get_endpoint_definitions() -> list[dict[str, Any]]:
    """Define endpoint metadata for /ui routes."""
    endpoints = [
        {
            "method": "GET",
            "path": "/ui/deliveries",
            "summary": "List delivery timelines",
            "description": "Query delivery timelines with optional filtering. Read-only endpoint.",
            "response_model": "DeliveryTimelineListResponse",
            "query_params": [
                {"name": "cursor", "type": "string", "required": False},
                {
                    "name": "limit",
                    "type": "integer",
                    "required": False,
                    "default": 25,
                    "min": 1,
                    "max": 100,
                },
                {"name": "start_time", "type": "datetime", "required": False},
                {"name": "end_time", "type": "datetime", "required": False},
                {"name": "status", "type": "DeliveryStatus", "required": False},
                {"name": "intent", "type": "NotificationIntent", "required": False},
                {"name": "delivery_mode", "type": "DeliveryMode", "required": False},
                {"name": "agent_id", "type": "uuid", "required": False},
                {"name": "autonomy_mode", "type": "AutonomyMode", "required": False},
                {"name": "notification_type", "type": "string", "required": False},
                {"name": "channel", "type": "Channel", "required": False},
            ],
            "error_codes": ["invalid_parameter"],
        },
        {
            "method": "GET",
            "path": "/ui/deliveries/{notification_id}",
            "summary": "Get delivery timeline",
            "description": "Get full delivery timeline for a specific notification. Read-only endpoint.",
            "response_model": "DeliveryTimelineResponse",
            "path_params": [
                {"name": "notification_id", "type": "uuid", "required": True},
            ],
            "error_codes": ["not_found"],
        },
        {
            "method": "GET",
            "path": "/ui/policies/effective",
            "summary": "Get effective policy",
            "description": "Get effective policy resolution for a notification type. Read-only endpoint.",
            "response_model": "EffectivePolicyResponse",
            "query_params": [
                {"name": "notification_type", "type": "string", "required": True},
                {"name": "intent", "type": "NotificationIntent", "required": True},
                {"name": "autonomy_mode", "type": "AutonomyMode", "required": True},
                {"name": "irreversible", "type": "boolean", "required": False, "default": False},
            ],
            "error_codes": ["invalid_parameter"],
        },
        {
            "method": "GET",
            "path": "/ui/invariants",
            "summary": "List system invariants",
            "description": "Get the system invariant registry. Read-only endpoint.",
            "response_model": "InvariantListResponse",
            "query_params": [
                {"name": "cursor", "type": "string", "required": False},
                {
                    "name": "limit",
                    "type": "integer",
                    "required": False,
                    "default": 25,
                    "min": 1,
                    "max": 100,
                },
                {"name": "severity", "type": "InvariantSeverity", "required": False},
                {"name": "enforcement_type", "type": "EnforcementType", "required": False},
                {"name": "status", "type": "InvariantStatus", "required": False},
                {"name": "search", "type": "string", "required": False},
            ],
            "error_codes": ["invalid_parameter"],
        },
        {
            "method": "GET",
            "path": "/ui/invariants/summary",
            "summary": "Get invariant summary",
            "description": "Get summary statistics for system invariants. Read-only endpoint.",
            "response_model": "InvariantSummaryResponse",
            "query_params": [],
            "error_codes": [],
        },
        {
            "method": "GET",
            "path": "/ui/audit",
            "summary": "List audit events",
            "description": "Query audit event stream with filtering. Read-only endpoint.",
            "response_model": "AuditEventListResponse",
            "query_params": [
                {"name": "cursor", "type": "string", "required": False},
                {
                    "name": "limit",
                    "type": "integer",
                    "required": False,
                    "default": 25,
                    "min": 1,
                    "max": 100,
                },
                {"name": "start_time", "type": "datetime", "required": False},
                {"name": "end_time", "type": "datetime", "required": False},
                {"name": "event_type", "type": "AuditEventType", "required": False},
                {"name": "notification_id", "type": "uuid", "required": False},
                {"name": "agent_id", "type": "uuid", "required": False},
                {"name": "autonomy_mode", "type": "AutonomyMode", "required": False},
                {"name": "correlation_id", "type": "string", "required": False},
            ],
            "error_codes": ["invalid_parameter", "invalid_cursor"],
        },
    ]

    # Sort endpoints by path for determinism
    return sorted(endpoints, key=lambda e: (e["path"], e["method"]))


def get_constants() -> dict[str, Any]:
    """Extract constants from notification.models."""
    from notification.models import (
        MESSAGE_MAX_LENGTH,
        TITLE_MAX_LENGTH,
    )

    return {
        "TITLE_MAX_LENGTH": TITLE_MAX_LENGTH,
        "MESSAGE_MAX_LENGTH": MESSAGE_MAX_LENGTH,
        "PAGINATION_DEFAULT_LIMIT": 25,
        "PAGINATION_MAX_LIMIT": 100,
    }


def generate_contract_snapshot() -> dict[str, Any]:
    """Generate the complete contract snapshot."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "UNS Console Contracts",
        "description": "Machine-readable contract snapshot for UNS Console /ui endpoints",
        "version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "scripts/generate_ui_contracts.py",
        "enums": get_enum_definitions(),
        "constants": get_constants(),
        "schemas": get_response_schemas(),
        "endpoints": get_endpoint_definitions(),
    }


def main() -> int:
    """Generate and write the contract snapshot."""
    # Determine output path
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    output_path = project_root / "docs" / "ui" / "contracts" / "ui-contracts.json"

    # Ensure directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Generate snapshot
        snapshot = generate_contract_snapshot()

        # Write to file with deterministic formatting
        with open(output_path, "w") as f:
            json.dump(snapshot, f, indent=2, sort_keys=False)
            f.write("\n")  # Trailing newline

        print(f"Generated contract snapshot: {output_path}")
        print(f"  Enums: {len(snapshot['enums'])}")
        print(f"  Schemas: {len(snapshot['schemas'])}")
        print(f"  Endpoints: {len(snapshot['endpoints'])}")

        return 0

    except Exception as e:
        print(f"Error generating contract snapshot: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
