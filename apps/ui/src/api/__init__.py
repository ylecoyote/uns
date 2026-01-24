"""API client module for UNS UI endpoints.

This module provides typed client classes for interacting with the UNS backend
read-only API endpoints. All API calls are GET requests only (read-only posture).

Endpoints supported:
- GET /api/v1/delivery-timelines - List delivery timelines with filtering
- GET /api/v1/notifications/{id}/delivery-timeline - Single delivery timeline
- GET /api/v1/policy-trace - Effective policy resolution trace
- GET /api/v1/invariants - List system invariants
- GET /api/v1/invariants/summary - Invariant summary statistics
- GET /api/v1/audit-events - List audit events
"""
