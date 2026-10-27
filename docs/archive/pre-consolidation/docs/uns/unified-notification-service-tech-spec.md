> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

> Historical note: This document is preserved from the UNS extraction phase. In current public product terminology, UNS maps to UNS Core and UNS Dashboard maps to UNS Console.

# Unified Notification Service (UNS) Technical Specification v2.0

**Spec Type:** Technical / Engineering Specification
**Derived From:** Functional Spec v2.0
**Audience:** Backend Engineers, Platform Engineers, QA
**Change Policy:** Breaking changes require Architecture Review
**Last Updated:** 2026-02-10

---

## 1. System Overview

### 1.1 Purpose

UNS is the **human-agent interrupt layer** - the communication bridge between autonomous agents and human operators. It implements:

- **Intent-based routing:** Notifications declare their semantic intent (SAFETY, GOVERNANCE, OPERATIONAL, INFORMATIONAL)
- **Delivery guarantees:** GUARANTEED notifications fail loudly; BEST_EFFORT notifications may fail silently
- **Autonomy awareness:** Every notification includes autonomy context (PREVIEW/SHADOW/LIVE mode, agent_id, plan_id)
- **Acknowledgment system:** SAFETY/GOVERNANCE notifications require human acknowledgment (ACKED, DISMISSED, TIMED_OUT)
- **Declarative policies:** Notification behavior defined in YAML, versioned, auditable
- **Decision coupling:** Link notifications to Why Layer (DecisionSnapshot, ExecutionSnapshot, SkipSnapshot)
- **Cognitive safety:** Deduplication protects human attention, not just system performance
- **Safety-path strictness:** SAFETY and GOVERNANCE intents never swallow errors

**Core contract:** When an agent needs human awareness, UNS ensures that message reaches the right human through the right channel with appropriate urgency — and confirms the human received it.

**Control plane boundary:** UNS operates entirely outside the execution data plane. It signals state changes, routes awareness to humans, and gates autonomy transitions — but never executes trades, blocks execution loops, or holds positions open. See func spec §1.4.

**GUARANTEED delivery semantics:** GUARANTEED delivery means the system will either deliver the notification, escalate to a higher-priority channel (e.g., PagerDuty), or surface visible system degradation. It does not mean infinite retries. The DLQ escalation handler (§3.3) enforces this invariant: GUARANTEED notifications that exhaust retries trigger emergency escalation, not silent failure.

**Design principle:** Use existing infrastructure (RQ, Redis) over new dependencies. *(See Implementation Note in 1.1.1 -- production uses async FastAPI, not RQ.)*

> **⚠️ Anti-Pattern Warning**
>
> **Do not use UNS acknowledgments to pause or delay trade execution.**
>
> Why this is dangerous: Introducing human latency into market-timed systems violates the control-plane boundary and can cause:
> - Order placement delays (slippage, missed fills)
> - Risk unwind logic delays (position exposure)
> - In-flight execution blocking (deadlocks, timeouts)
>
> UNS acknowledgments may gate **autonomy state transitions** (e.g., PREVIEW→SHADOW, policy activation) but must never block execution loops, order routing, or position management. See `block_autonomy_until_ack` semantics in §4.6.

### 1.1.1 Architecture Trade-off: RQ vs Redis Streams

> **Implementation Note (2026-02-10):** The production implementation uses direct async FastAPI delivery orchestration via `process_and_deliver()` in `src/notification/service.py`, not RQ or Redis Streams. The standalone FastAPI application lives in `src/notification/main.py`. Redis is used for deduplication (SETNX + TTL) and rate limiting (token bucket) only. Async adapters for Slack, Email, WebSocket, and PagerDuty live in `src/notification/adapters/`. The trade-off analysis below was from the design phase and does not reflect the final architecture.

UNS uses **RQ (Redis Queue)** rather than Redis Streams + FastStream. This is a deliberate trade-off:

| Factor | RQ (Chosen) | Redis Streams |
|--------|-------------|---------------|
| **Latency** | ~10-50ms | Sub-millisecond |
| **Complexity** | Simple, well-understood | Consumer groups, more ops burden |
| **Existing infra** | Already deployed | New dependency |
| **Horizontal scaling** | Worker pools | Consumer groups |
| **Persistence** | Job results in Redis | Built-in stream persistence |

**Why RQ for v2.0:**

1. **UNS is control plane, not data plane** — 10-50ms latency is acceptable for human-facing notifications. We're not in the execution hot path.

2. **Operational simplicity** — RQ workers are already deployed and understood. Adding Redis Streams + FastStream increases ops surface area.

3. **Sufficient for current scale** — RQ handles thousands of jobs/second. UNS notification volume is orders of magnitude lower.

4. **Migration path exists** — If latency becomes a bottleneck, we can migrate to Redis Streams without changing the SDK interface. The SDK's `send()` method abstracts the queue implementation.

**When to reconsider:** If notification latency becomes a bottleneck (measure via `uns_delivery_latency_seconds` metric) or if we need guaranteed ordering across notification types.

### 1.2 Architecture Diagram

> **Implementation Note (2026-02-10):** The diagram below reflects the original RQ-based design. The production architecture replaces the RQ Worker Process with direct async FastAPI delivery orchestration in `src/notification/service.py` (via `process_and_deliver()`). The Deduplicator, Rate Limiter, Delivery pipeline, and Adapters are accurate, but they run as async coroutines within the FastAPI process rather than in a separate RQ worker. Priority queues (`notify:high`, `notify:normal`, `notify:low`) are not used in production.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Producers                                    │
│                                                                      │
│  ExecutionAlerts   WhaleService   AgentGovernor   AutonomyController│
│        │                │               │                │          │
│        └────────────────┴───────────────┴────────────────┘          │
│                                  │                                   │
│                                  ▼                                   │
│                        ┌─────────────────┐                          │
│                        │ NotificationSDK │                          │
│                        │  sdk.send()     │                          │
│                        │ + autonomy_ctx  │                          │
│                        └────────┬────────┘                          │
└─────────────────────────────────┼───────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Policy Registry + Redis + RQ                       │
│                                                                      │
│   ┌──────────────────┐                                              │
│   │ NotificationPolicy│  YAML-based declarative behavior            │
│   │    (PostgreSQL)   │  - channels by autonomy_mode                │
│   └────────┬─────────┘  - require_ack by intent                     │
│            │                                                         │
│            ▼                                                         │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│   │ notify:high  │  │notify:normal │  │  notify:low  │             │
│   │   (RQ)       │  │    (RQ)      │  │    (RQ)      │             │
│   └──────┬───────┘  └──────┬───────┘  └──────┬───────┘             │
│          │                 │                 │                      │
│          └─────────────────┼─────────────────┘                      │
│                            │                                        │
│                            ▼                                        │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │                  RQ Worker Process                           │  │
│   │                                                              │  │
│   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │  │
│   │  │ Deduplicator │→│ Rate Limiter │→│   Delivery   │       │  │
│   │  └──────────────┘  └──────────────┘  └──────┬───────┘       │  │
│   │                                             │                │  │
│   └─────────────────────────────────────────────┼────────────────┘  │
│                                                 │                   │
│   ┌─────────────────────────────────────────────┼────────────────┐  │
│   │                    Adapters                  │                │  │
│   │                                             ▼                │  │
│   │  ┌────────┐  ┌────────┐  ┌───────────┐  ┌───────────┐       │  │
│   │  │ Slack  │  │ Email  │  │ WebSocket │  │ PagerDuty │       │  │
│   │  └────────┘  └────────┘  └───────────┘  └───────────┘       │  │
│   └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│   ┌──────────────────┐  ┌──────────────────┐  ┌─────────────────┐   │
│   │ Failed Job Queue │  │ notification_audit│  │ ack_timeout_job │   │
│   │     (DLQ)        │  │    (PostgreSQL)   │  │     (RQ)        │   │
│   └──────────────────┘  └──────────────────┘  └─────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Acknowledgment Flow                               │
│                                                                      │
│   UI (WebSocket/Slack Button)                                        │
│            │                                                         │
│            ▼                                                         │
│   ┌──────────────────┐     ┌──────────────────┐                     │
│   │  POST /v1/notif/ │────▶│  AckEventEmitter │────▶ Agent Learning │
│   │    {id}/ack      │     │                  │────▶ Audit Log      │
│   └──────────────────┘     └──────────────────┘────▶ Governance     │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. File Structure

### 2.1 Standalone-First Architecture (New in v2.0)

UNS is designed as a **standalone service** with optional ATP integration. This architecture provides:

- **Clean separation:** Core UNS has no ATP imports
- **Testability:** Unit tests don't require ATP mocks
- **Reusability:** Can be used by non-ATP systems
- **Dependency injection:** ATP-specific behavior injected at runtime

### 2.2 Directory Layout

```
src/
├── notification/                     # CORE UNS (ATP-AGNOSTIC)
│   ├── __init__.py
│   ├── interfaces.py                 # Protocol definitions (NEW)
│   ├── sdk.py                        # NotificationSDK with dependency injection
│   ├── factory.py                    # SDK factory: create_sdk(integration="standalone|atp|test")
│   ├── service.py                    # Core delivery logic
│   ├── deduplication.py              # Dedup with Redis SETNX
│   ├── rate_limiting.py              # Token bucket implementation
│   ├── models.py                     # Pydantic models (Notification, AutonomyContext, etc.)
│   ├── config.py                     # Configuration
│   ├── policies.py                   # NotificationPolicy registry and loading
│   ├── acknowledgment.py             # Acknowledgment handling and timeout jobs
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py                   # Abstract adapter interface
│   │   ├── slack.py                  # Slack webhook adapter (with ack buttons)
│   │   ├── email.py                  # SMTP adapter
│   │   ├── websocket.py              # WebSocket broadcast adapter (with ack support)
│   │   └── pagerduty.py              # PagerDuty Events API adapter
│   │
│   └── integrations/                 # ATP-SPECIFIC INTEGRATION MODULE (NEW)
│       ├── __init__.py               # get_atp_sdk() factory
│       ├── atp_context.py            # ATPContextProvider implementation
│       ├── atp_callbacks.py          # ATPAckCallback implementation
│       ├── governor_hooks.py         # Agent Governor → UNS notifications
│       ├── execution_alerts.py       # ExecutionAlerts migration shim
│       └── why_layer.py              # Decision Snapshot linking
│
├── mcp_server/
│   └── routes_notification.py        # API routes for ack, status, policies
├── db/
│   └── models.py                     # Add NotificationAuditModel, NotificationPolicyModel
└── tests/
    └── notification/
        ├── __init__.py
        ├── test_sdk.py               # Tests with DefaultContextProvider (no ATP deps)
        ├── test_service.py
        ├── test_deduplication.py
        ├── test_rate_limiting.py
        ├── test_acknowledgment.py
        ├── test_policies.py
        ├── test_adapters.py
        └── test_integrations/        # ATP integration tests (NEW)
            ├── test_atp_context.py
            ├── test_governor_hooks.py
            └── test_execution_alerts.py
```

### 2.3 Interface Definitions (`interfaces.py`)

```python
"""
UNS Integration Interfaces

These Protocol classes define how external systems (like ATP) integrate with UNS.
The core UNS code depends on these interfaces, not concrete implementations.
"""

from typing import Protocol, Optional
from uuid import UUID


class NotificationContextProvider(Protocol):
    """
    Provides execution context to UNS.

    ATP implements this to provide autonomy mode, agent ID, etc.
    Standalone mode uses DefaultContextProvider with safe defaults.
    """

    def get_autonomy_mode(self) -> str:
        """Return current autonomy mode (PREVIEW/SHADOW/LIVE)."""
        ...

    def get_agent_id(self) -> Optional[UUID]:
        """Return current agent ID if in agent context."""
        ...

    def get_plan_id(self) -> Optional[UUID]:
        """Return current plan ID if available."""
        ...

    def get_decision_snapshot_id(self) -> Optional[UUID]:
        """Return decision snapshot ID for Why Layer linking."""
        ...


class AcknowledgmentCallback(Protocol):
    """
    Handles acknowledgment events.

    ATP implements this to update Governor state, emit telemetry, etc.
    Standalone mode may omit this (None).
    """

    async def on_ack(
        self,
        notification_id: UUID,
        ack_status: str,
        acked_by: str,
        metadata: dict,
    ) -> None:
        """Called when notification is acknowledged."""
        ...


class DefaultContextProvider:
    """Default context provider for standalone usage."""

    def get_autonomy_mode(self) -> str:
        return "LIVE"  # Safest default

    def get_agent_id(self) -> Optional[UUID]:
        return None

    def get_plan_id(self) -> Optional[UUID]:
        return None

    def get_decision_snapshot_id(self) -> Optional[UUID]:
        return None
```

### 2.4 SDK Dependency Injection

The `NotificationSDK` accepts optional dependencies via constructor:

```python
class NotificationSDK:
    """
    Core notification SDK - ATP-agnostic.

    ATP-specific behavior is injected via context_provider and ack_callback.
    """

    def __init__(
        self,
        context_provider: Optional[NotificationContextProvider] = None,
        ack_callback: Optional[AcknowledgmentCallback] = None,
        config: Optional[NotificationConfig] = None,
    ):
        self._context_provider = context_provider or DefaultContextProvider()
        self._ack_callback = ack_callback
        self._config = config or NotificationConfig()
```

### 2.5 Usage Modes

| Mode | Factory Call | Context Provider | Ack Callback |
|------|-------------|------------------|--------------|
| **Standalone** | `NotificationSDK()` | `DefaultContextProvider` | None |
| **ATP** | `get_atp_sdk()` | `ATPContextProvider` | `ATPAckCallback` |
| **Test** | `create_sdk("test")` | `MockContextProvider` | `MockAckCallback` |

```python
# Standalone (no ATP dependencies)
from src.notification.sdk import NotificationSDK
sdk = NotificationSDK()
sdk.send(notification_type="alert", intent=OPERATIONAL, ...)

# ATP integration
from src.notification.integrations import get_atp_sdk
sdk = get_atp_sdk()
sdk.send_safety(notification_type="safety.kill_switch", ...)

# Testing
from src.notification.factory import create_sdk
sdk = create_sdk("test")
```

---

## 3. Phase 1: Foundation

### 3.1 Models (`src/notification/models.py`)

```python
"""
Notification Models - Pydantic V2 schemas

Follows Agent Governor pattern for consistency.
v1.2: Added AutonomyMode, AutonomyContext, AckStatus, acknowledgment fields
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class NotificationIntent(str, Enum):
    """
    Semantic routing intent - what kind of human attention is needed.

    Intent determines:
    - Default channel routing
    - Error handling behavior (strict vs lenient)
    - Escalation paths
    - Acknowledgment requirements
    """
    SAFETY = "SAFETY"           # Trading safety events - halt, margin, breach
    GOVERNANCE = "GOVERNANCE"   # Policy/autonomy changes - approvals, rejections
    OPERATIONAL = "OPERATIONAL" # Execution metrics - slippage, fill rates
    INFORMATIONAL = "INFORMATIONAL"  # Summaries, completions, FYI


class DeliveryMode(str, Enum):
    """
    Delivery guarantee level.

    GUARANTEED: Must succeed or escalate loudly. Used for SAFETY/GOVERNANCE.
    BEST_EFFORT: May fail silently. Used for OPERATIONAL/INFORMATIONAL.
    """
    GUARANTEED = "GUARANTEED"   # Fail loudly, escalate on failure
    BEST_EFFORT = "BEST_EFFORT" # Log and continue on failure


class Priority(str, Enum):
    """
    Notification priority levels.

    Note: Priority is now derived from Intent for most cases.
    Explicit priority overrides Intent-based defaults.
    """
    HIGH = "HIGH"        # Kill switch, margin calls, circuit breaker
    NORMAL = "NORMAL"    # Execution alerts, whale alerts, approvals
    LOW = "LOW"          # Info, summaries, completions


class Channel(str, Enum):
    """Delivery channels"""
    SLACK = "SLACK"
    EMAIL = "EMAIL"
    WEBSOCKET = "WEBSOCKET"
    PAGERDUTY = "PAGERDUTY"


class DeliveryStatus(str, Enum):
    """Notification delivery status"""
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    DEDUPLICATED = "DEDUPLICATED"
    RATE_LIMITED = "RATE_LIMITED"
    ESCALATED = "ESCALATED"  # GUARANTEED delivery escalated due to failure


class AutonomyMode(str, Enum):
    """
    Autonomy mode context for notifications.

    Different modes affect notification routing:
    - PREVIEW: WebSocket only (low noise)
    - SHADOW: OPERATIONAL → WebSocket, GOVERNANCE → Slack
    - LIVE: Full routing per intent + escalation
    """
    PREVIEW = "PREVIEW"
    SHADOW = "SHADOW"
    LIVE = "LIVE"


class AckStatus(str, Enum):
    """
    Acknowledgment status for notifications requiring human confirmation.

    Used for SAFETY and GOVERNANCE intents to confirm human awareness.
    """
    PENDING = "PENDING"       # Delivered, awaiting acknowledgment
    ACKED = "ACKED"           # Human acknowledged (saw and understood)
    DISMISSED = "DISMISSED"   # Human dismissed (saw but chose not to act)
    TIMED_OUT = "TIMED_OUT"   # No response within timeout window


class AutonomyContext(BaseModel):
    """
    Autonomy context embedded in every notification.

    Provides mode + agent/plan context for routing decisions
    and linking to Why Layer artifacts.
    """
    autonomy_mode: AutonomyMode = Field(
        ...,
        description="Current operating mode (PREVIEW, SHADOW, LIVE)"
    )
    agent_id: UUID = Field(
        ...,
        description="Agent that triggered the notification"
    )
    plan_id: Optional[UUID] = Field(
        default=None,
        description="Associated plan (if any)"
    )
    decision_snapshot_id: Optional[UUID] = Field(
        default=None,
        description="Why Layer reference for decision context"
    )
    execution_snapshot_id: Optional[UUID] = Field(
        default=None,
        description="Why Layer reference for execution context"
    )
    skip_snapshot_id: Optional[UUID] = Field(
        default=None,
        description="Why Layer reference for skip context"
    )


class NotificationType(str, Enum):
    """
    Notification types - maps to sources.

    Naming convention: {domain}.{event}
    """
    # Execution domain
    EXECUTION_SLIPPAGE = "execution.slippage"
    EXECUTION_ERROR_RATE = "execution.error_rate"
    EXECUTION_FILL_RATE = "execution.fill_rate"
    EXECUTION_COST = "execution.cost"
    EXECUTION_DAILY_SUMMARY = "execution.daily_summary"
    EXECUTION_TRADE_SKIPPED = "execution.trade_skipped"

    # Safety domain
    SAFETY_KILL_SWITCH = "safety.kill_switch"
    SAFETY_MARGIN_CALL = "safety.margin_call"
    SAFETY_PORTFOLIO_BREACH = "safety.portfolio_breach"
    SAFETY_CIRCUIT_BREAKER = "safety.circuit_breaker"

    # Governance domain
    GOVERNANCE_APPROVAL_REQUIRED = "governance.approval_required"
    GOVERNANCE_APPROVED = "governance.approved"
    GOVERNANCE_REJECTED = "governance.rejected"
    GOVERNANCE_POLICY_ACTIVATED = "governance.policy_activated"
    GOVERNANCE_POLICY_RETIRED = "governance.policy_retired"
    GOVERNANCE_AUTONOMY_CHANGE = "governance.autonomy_change"
    GOVERNANCE_MODE_CHANGE = "governance.mode_change"

    # Analysis domain
    ANALYSIS_WHALE_ACCUMULATION = "analysis.whale_accumulation"
    ANALYSIS_VALIDATION_FAILURE = "analysis.validation_failure"

    # System domain
    SYSTEM_BACKTEST_COMPLETE = "system.backtest_complete"
    SYSTEM_AGENT_SESSION = "system.agent_session"
    SYSTEM_DLQ_ALERT = "system.dlq_alert"
    SYSTEM_DEDUP_SUMMARY = "system.dedup_summary"
    SYSTEM_ACK_TIMEOUT = "system.ack_timeout"


class Notification(BaseModel):
    """
    Core notification model.

    This is the canonical notification format used throughout UNS.
    Intent and delivery_mode are primary routing attributes; priority is derived.

    v1.2: Added autonomy_context and acknowledgment fields
    """
    notification_id: UUID = Field(default_factory=uuid4)
    notification_type: NotificationType

    # Intent-based routing
    intent: NotificationIntent = Field(
        ...,
        description="Semantic intent - determines routing and error handling"
    )
    delivery_mode: DeliveryMode = Field(
        default=DeliveryMode.BEST_EFFORT,
        description="GUARANTEED fails loudly, BEST_EFFORT may fail silently"
    )
    irreversible: bool = Field(
        default=False,
        description="True if notification relates to an irreversible action (triggers PagerDuty)"
    )

    # Autonomy context (new in v1.2)
    autonomy_context: AutonomyContext = Field(
        ...,
        description="Current operating mode and agent/plan identifiers"
    )

    # Acknowledgment (new in v1.2)
    require_ack: bool = Field(
        default=False,
        description="True if human acknowledgment is required"
    )
    ack_timeout_minutes: int = Field(
        default=15,
        description="Minutes before ack times out (if require_ack=True)"
    )
    ack_status: AckStatus = Field(
        default=AckStatus.PENDING,
        description="Current acknowledgment status"
    )
    acked_at: Optional[datetime] = Field(
        default=None,
        description="When acknowledged"
    )
    acked_by: Optional[str] = Field(
        default=None,
        description="User who acknowledged"
    )

    # Priority (derived from intent by default, can be overridden)
    priority: Priority = Priority.NORMAL

    # Content
    title: str = Field(..., max_length=200)
    message: str = Field(..., max_length=4000)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Routing
    channels: List[Channel] = Field(default_factory=lambda: [Channel.SLACK])

    # Deduplication (cognitive safety)
    dedup_key: Optional[str] = None  # Auto-generated if not provided

    # Tracking
    source: str = Field(..., description="Producer identifier")
    correlation_id: Optional[str] = None  # Links related notifications

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True

    def model_post_init(self, __context) -> None:
        """Derive defaults from intent and autonomy_mode if not explicitly set."""
        # Derive priority from intent if using default
        if self.priority == Priority.NORMAL:
            intent_priority = {
                NotificationIntent.SAFETY: Priority.HIGH,
                NotificationIntent.GOVERNANCE: Priority.HIGH,
                NotificationIntent.OPERATIONAL: Priority.NORMAL,
                NotificationIntent.INFORMATIONAL: Priority.LOW,
            }
            self.priority = intent_priority.get(self.intent, Priority.NORMAL)

        # Derive delivery_mode from intent if using default
        if self.delivery_mode == DeliveryMode.BEST_EFFORT:
            if self.intent in (NotificationIntent.SAFETY, NotificationIntent.GOVERNANCE):
                self.delivery_mode = DeliveryMode.GUARANTEED

        # Derive require_ack from intent (SAFETY always requires ack in LIVE mode)
        if not self.require_ack and self.autonomy_context.autonomy_mode == AutonomyMode.LIVE:
            if self.intent == NotificationIntent.SAFETY:
                self.require_ack = True


class NotificationResult(BaseModel):
    """Result of notification delivery attempt"""
    notification_id: UUID
    status: DeliveryStatus
    channels_attempted: List[Channel]
    channels_succeeded: List[Channel]
    channels_failed: List[Channel]
    failure_reason: Optional[str] = None
    retry_count: int = 0
    delivered_at: Optional[datetime] = None
    # Ack tracking
    require_ack: bool = False
    ack_status: AckStatus = AckStatus.PENDING
    ack_timeout_at: Optional[datetime] = None


class AckEvent(BaseModel):
    """
    Acknowledgment event emitted when humans respond to notifications.

    Used for:
    - Audit trail
    - Agent learning (did human act on this?)
    - Governance enforcement
    - Trust calibration
    """
    notification_id: UUID
    ack_status: AckStatus
    acked_by: Optional[str] = None
    acked_at: datetime = Field(default_factory=datetime.utcnow)
    response_time_seconds: Optional[int] = None  # Time from delivery to ack
    autonomy_context: AutonomyContext
    intent: NotificationIntent
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

### 3.2 SDK (`src/notification/sdk.py`)

> **Implementation Note (2026-02-10):** The production SDK (`src/notification/sdk.py`) uses direct async invocation rather than enqueuing to RQ. The `from rq import Queue` and RQ-based `send()` logic shown below are from the design phase. In production, the SDK calls `process_and_deliver()` directly within the FastAPI async context.

```python
"""
Notification SDK - Simple interface for producers

v1.2: Added autonomy_context parameter, mode-dependent routing, policy support

Usage:
    from src.notification.sdk import NotificationSDK, NotificationIntent, AutonomyContext, AutonomyMode

    sdk = NotificationSDK()

    # Create autonomy context (required for all notifications)
    ctx = AutonomyContext(
        autonomy_mode=AutonomyMode.LIVE,
        agent_id=agent_id,
        plan_id=plan_id,
        decision_snapshot_id=snapshot_id,  # Links to Why Layer
    )

    # Simple usage - intent + context determines routing
    job_id = sdk.send(
        notification_type="execution.slippage",
        intent=NotificationIntent.OPERATIONAL,
        autonomy_context=ctx,
        title="Slippage Alert",
        message="Average slippage 25.5 bps exceeds threshold of 20 bps",
        source="execution_alerts",
    )

    # Safety notification - GUARANTEED delivery, PagerDuty escalation, require_ack
    job_id = sdk.send(
        notification_type="safety.kill_switch",
        intent=NotificationIntent.SAFETY,
        autonomy_context=ctx,
        title="KILL SWITCH ACTIVATED",
        message="Trading halted by operator",
        source="autonomy_controller",
        irreversible=True,  # Triggers PagerDuty
        metadata={"triggered_by": "operator@example.com"},
    )
"""

import hashlib
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from rq import Queue

from src.db.dependencies import create_redis
from src.notification.models import (
    AckStatus,
    AutonomyContext,
    AutonomyMode,
    Channel,
    DeliveryMode,
    Notification,
    NotificationIntent,
    NotificationType,
    Priority,
)


class NotificationSDK:
    """
    Lightweight SDK for sending notifications.

    Design principles:
    - Intent-first: Intent determines routing and error behavior
    - Autonomy-aware: Routing varies by PREVIEW/SHADOW/LIVE mode
    - Policy-driven: Behavior can be overridden by declarative policies
    - Non-blocking (queues to RQ)
    - Simple interface (most params optional)
    - Fail-safe for BEST_EFFORT, fail-loud for GUARANTEED
    """

    # Default channels by intent (semantic routing) for LIVE mode
    DEFAULT_CHANNELS_BY_INTENT = {
        NotificationIntent.SAFETY: [Channel.SLACK, Channel.WEBSOCKET],
        NotificationIntent.GOVERNANCE: [Channel.SLACK, Channel.WEBSOCKET],
        NotificationIntent.OPERATIONAL: [Channel.SLACK],
        NotificationIntent.INFORMATIONAL: [Channel.WEBSOCKET],
    }

    # Mode-dependent channel overrides (new in v1.2)
    MODE_CHANNEL_OVERRIDES = {
        AutonomyMode.PREVIEW: {
            # PREVIEW: WebSocket only for all intents (low noise)
            NotificationIntent.SAFETY: [Channel.WEBSOCKET],
            NotificationIntent.GOVERNANCE: [Channel.WEBSOCKET],
            NotificationIntent.OPERATIONAL: [Channel.WEBSOCKET],
            NotificationIntent.INFORMATIONAL: [Channel.WEBSOCKET],
        },
        AutonomyMode.SHADOW: {
            # SHADOW: OPERATIONAL → WebSocket, GOVERNANCE → Slack
            NotificationIntent.SAFETY: [Channel.SLACK, Channel.WEBSOCKET],
            NotificationIntent.GOVERNANCE: [Channel.SLACK, Channel.WEBSOCKET],
            NotificationIntent.OPERATIONAL: [Channel.WEBSOCKET],
            NotificationIntent.INFORMATIONAL: [Channel.WEBSOCKET],
        },
        # LIVE: Uses DEFAULT_CHANNELS_BY_INTENT
    }

    # Channels added when irreversible=True (LIVE mode only)
    IRREVERSIBLE_ESCALATION_CHANNELS = [Channel.PAGERDUTY]

    # Ack requirements by intent (LIVE mode only)
    DEFAULT_REQUIRE_ACK = {
        NotificationIntent.SAFETY: True,       # Always require ack
        NotificationIntent.GOVERNANCE: False,  # Configurable via policy
        NotificationIntent.OPERATIONAL: False,
        NotificationIntent.INFORMATIONAL: False,
    }

    # Default ack timeouts by intent (minutes)
    DEFAULT_ACK_TIMEOUT = {
        NotificationIntent.SAFETY: 15,
        NotificationIntent.GOVERNANCE: 30,
    }

    # Queue names by priority
    QUEUE_NAMES = {
        Priority.HIGH: "notify:high",
        Priority.NORMAL: "notify:normal",
        Priority.LOW: "notify:low",
    }

    def __init__(self, redis_client=None):
        """
        Initialize SDK.

        Args:
            redis_client: Optional Redis client. Uses default if not provided.
        """
        self._redis = redis_client
        self._queues: Dict[Priority, Queue] = {}

    @property
    def redis(self):
        """Lazy Redis connection"""
        if self._redis is None:
            self._redis = create_redis()
        return self._redis

    def _get_queue(self, priority: Priority) -> Queue:
        """Get or create queue for priority level"""
        if priority not in self._queues:
            self._queues[priority] = Queue(
                self.QUEUE_NAMES[priority],
                connection=self.redis,
            )
        return self._queues[priority]

    def _generate_dedup_key(
        self,
        notification_type: str,
        source: str,
        message: str,
        autonomy_mode: AutonomyMode,
    ) -> str:
        """
        Generate deduplication key from notification content.

        Note: autonomy_mode is included so PREVIEW/LIVE of same event are separate.
        """
        truncated = message[:100] if len(message) > 100 else message
        content = f"{notification_type}:{source}:{autonomy_mode.value}:{truncated}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _get_channels_for_mode(
        self,
        intent: NotificationIntent,
        autonomy_mode: AutonomyMode,
        irreversible: bool,
    ) -> List[Channel]:
        """
        Get channels based on intent and autonomy mode.

        Mode-dependent routing:
        - PREVIEW: WebSocket only
        - SHADOW: Reduced escalation
        - LIVE: Full routing + PagerDuty for irreversible
        """
        if autonomy_mode in self.MODE_CHANNEL_OVERRIDES:
            channels = list(self.MODE_CHANNEL_OVERRIDES[autonomy_mode].get(
                intent, [Channel.WEBSOCKET]
            ))
        else:
            # LIVE mode: full routing
            channels = list(self.DEFAULT_CHANNELS_BY_INTENT.get(intent, [Channel.SLACK]))
            # Add PagerDuty for irreversible actions in LIVE mode
            if irreversible:
                for esc_channel in self.IRREVERSIBLE_ESCALATION_CHANNELS:
                    if esc_channel not in channels:
                        channels.append(esc_channel)
        return channels

    def send(
        self,
        notification_type: Union[str, NotificationType],
        intent: NotificationIntent,
        autonomy_context: AutonomyContext,
        title: str,
        message: str,
        source: str,
        delivery_mode: Optional[DeliveryMode] = None,
        irreversible: bool = False,
        require_ack: Optional[bool] = None,
        ack_timeout_minutes: Optional[int] = None,
        priority: Optional[Priority] = None,
        channels: Optional[List[Channel]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        dedup_key: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Queue a notification for delivery.

        Args:
            notification_type: Type of notification (e.g., "execution.slippage")
            intent: Semantic intent (SAFETY, GOVERNANCE, OPERATIONAL, INFORMATIONAL)
            autonomy_context: Current operating mode and agent/plan identifiers (REQUIRED)
            title: Short title (max 200 chars)
            message: Full message (max 4000 chars)
            source: Producer identifier (e.g., "execution_alerts")
            delivery_mode: GUARANTEED or BEST_EFFORT (derived from intent if not set)
            irreversible: True if action is irreversible (triggers PagerDuty in LIVE)
            require_ack: True if human acknowledgment required (derived from intent/mode if not set)
            ack_timeout_minutes: Minutes before ack times out (default varies by intent)
            priority: HIGH, NORMAL, or LOW (derived from intent if not set)
            channels: Target channels (defaults based on intent + mode + irreversibility)
            metadata: Additional data (will be JSON serialized)
            dedup_key: Custom dedup key (auto-generated if not provided)
            correlation_id: Links related notifications

        Returns:
            Job ID string if queued, None if failed (BEST_EFFORT only)

        Raises:
            For GUARANTEED delivery mode: Re-raises after attempting direct delivery
            For BEST_EFFORT: Nothing - fails silently with logging
        """
        from src.common.logging import get_logger
        logger = get_logger(__name__)

        try:
            # ============================================================
            # PRODUCER CONTRACT VALIDATION (v1.2)
            # All notifications MUST include autonomy_context - this is a
            # hard guard against producer misuse per func spec §2.3
            # ============================================================
            if autonomy_context is None:
                raise ValueError(
                    "autonomy_context is required. UNS cannot route "
                    "notifications without autonomy awareness. "
                    "See func spec §2.3 Producer Contract."
                )
            if autonomy_context.autonomy_mode is None:
                raise ValueError(
                    "autonomy_context.autonomy_mode is required. "
                    "Notifications must declare PREVIEW, SHADOW, or LIVE mode."
                )
            if autonomy_context.agent_id is None:
                raise ValueError(
                    "autonomy_context.agent_id is required. "
                    "Notifications must be attributable to a specific agent."
                )

            # Convert string to enum if needed
            if isinstance(notification_type, str):
                notification_type = NotificationType(notification_type)

            autonomy_mode = autonomy_context.autonomy_mode

            # ================================================================
            # POLICY LOOKUP (per team feedback)
            # Look up policy for this notification_type. If found, policy
            # overrides SDK defaults for channels, require_ack, etc.
            # SDK defaults are fallback when no policy exists.
            # ================================================================
            policy = None
            try:
                from src.notification.policies import get_policy_registry
                registry = get_policy_registry()
                # Use sync get since SDK.send() is sync
                policy = registry.get_sync(notification_type.value)
                if policy:
                    logger.debug(
                        "Found policy for notification",
                        notification_type=notification_type.value,
                        policy_version=policy.version,
                    )
            except Exception as e:
                # Policy lookup failure is not fatal - fall back to SDK defaults
                logger.warning(
                    "Policy lookup failed, using SDK defaults",
                    notification_type=notification_type.value,
                    error=str(e),
                )

            # Derive delivery_mode from policy > intent if not specified
            if delivery_mode is None:
                if policy:
                    delivery_mode = policy.delivery_mode
                elif intent in (NotificationIntent.SAFETY, NotificationIntent.GOVERNANCE):
                    delivery_mode = DeliveryMode.GUARANTEED
                else:
                    delivery_mode = DeliveryMode.BEST_EFFORT

            # Derive priority from intent if not specified (policies don't override priority)
            if priority is None:
                intent_priority = {
                    NotificationIntent.SAFETY: Priority.HIGH,
                    NotificationIntent.GOVERNANCE: Priority.HIGH,
                    NotificationIntent.OPERATIONAL: Priority.NORMAL,
                    NotificationIntent.INFORMATIONAL: Priority.LOW,
                }
                priority = intent_priority.get(intent, Priority.NORMAL)

            # Derive channels from policy > SDK defaults if not specified
            if channels is None:
                if policy:
                    # Policy provides mode-aware channel overrides
                    channels = policy.get_channels_for_mode(autonomy_mode)
                else:
                    channels = self._get_channels_for_mode(intent, autonomy_mode, irreversible)

            # Derive require_ack from policy > SDK defaults if not specified
            if require_ack is None:
                if policy:
                    require_ack = policy.get_require_ack_for_mode(autonomy_mode)
                elif autonomy_mode == AutonomyMode.LIVE:
                    require_ack = self.DEFAULT_REQUIRE_ACK.get(intent, False)
                else:
                    # Non-LIVE modes don't require ack
                    require_ack = False

            # Derive ack_timeout from intent if not specified
            if ack_timeout_minutes is None:
                ack_timeout_minutes = self.DEFAULT_ACK_TIMEOUT.get(intent, 15)

            # Generate dedup key if not provided (includes autonomy_mode)
            if dedup_key is None:
                dedup_key = self._generate_dedup_key(
                    notification_type.value,
                    source,
                    message,
                    autonomy_mode,
                )

            # Create notification
            notification = Notification(
                notification_type=notification_type,
                intent=intent,
                delivery_mode=delivery_mode,
                irreversible=irreversible,
                autonomy_context=autonomy_context,
                require_ack=require_ack,
                ack_timeout_minutes=ack_timeout_minutes,
                ack_status=AckStatus.PENDING,
                priority=priority,
                title=title,
                message=message,
                metadata=metadata or {},
                channels=channels,
                dedup_key=dedup_key,
                source=source,
                correlation_id=correlation_id,
            )

            # Queue for delivery
            queue = self._get_queue(priority)
            job = queue.enqueue(
                "src.notification.service.deliver",
                notification.model_dump(mode="json"),
                retry=3,  # RQ built-in retry
                job_timeout=60,  # 1 minute timeout
                result_ttl=3600,  # Keep result for 1 hour
            )

            logger.info(
                "Notification queued",
                notification_id=str(notification.notification_id),
                notification_type=notification_type.value,
                intent=intent.value,
                autonomy_mode=autonomy_mode.value,
                require_ack=require_ack,
                priority=priority.value,
                job_id=job.id,
            )

            return job.id

        except Exception as e:
            logger.error(
                "Failed to queue notification",
                error=str(e),
                notification_type=str(notification_type),
                intent=intent.value,
                autonomy_mode=autonomy_context.autonomy_mode.value,
            )

            # GUARANTEED delivery: attempt direct delivery, then re-raise
            if delivery_mode == DeliveryMode.GUARANTEED:
                logger.warning(
                    "GUARANTEED delivery failed to queue - attempting direct delivery",
                    notification_type=str(notification_type),
                )
                try:
                    from src.notification.service import deliver_direct
                    deliver_direct(notification.model_dump(mode="json"))
                    return None  # Direct delivery succeeded
                except Exception as fallback_error:
                    logger.critical(
                        "GUARANTEED notification failed both queue and direct delivery",
                        error=str(fallback_error),
                        notification_type=str(notification_type),
                        intent=intent.value,
                    )
                    # Re-raise for GUARANTEED - never swallow errors
                    raise RuntimeError(
                        f"GUARANTEED notification delivery failed: {e}"
                    ) from e

            # BEST_EFFORT delivery: log and return None (fail silently)
            return None

    def send_safety(
        self,
        notification_type: Union[str, NotificationType],
        autonomy_context: AutonomyContext,
        title: str,
        message: str,
        source: str,
        irreversible: bool = False,
        **kwargs,
    ) -> Optional[str]:
        """
        Convenience method for SAFETY intent notifications.

        GUARANTEED delivery - will raise on failure.
        In LIVE mode: require_ack=True, channels include PagerDuty if irreversible
        """
        return self.send(
            notification_type=notification_type,
            intent=NotificationIntent.SAFETY,
            autonomy_context=autonomy_context,
            title=title,
            message=message,
            source=source,
            irreversible=irreversible,
            **kwargs,
        )

    def send_governance(
        self,
        notification_type: Union[str, NotificationType],
        autonomy_context: AutonomyContext,
        title: str,
        message: str,
        source: str,
        irreversible: bool = False,
        **kwargs,
    ) -> Optional[str]:
        """
        Convenience method for GOVERNANCE intent notifications.

        GUARANTEED delivery - will raise on failure.
        """
        return self.send(
            notification_type=notification_type,
            intent=NotificationIntent.GOVERNANCE,
            autonomy_context=autonomy_context,
            title=title,
            message=message,
            source=source,
            irreversible=irreversible,
            **kwargs,
        )

    def send_operational(
        self,
        notification_type: Union[str, NotificationType],
        autonomy_context: AutonomyContext,
        title: str,
        message: str,
        source: str,
        **kwargs,
    ) -> Optional[str]:
        """
        Convenience method for OPERATIONAL intent notifications.

        BEST_EFFORT delivery - may fail silently.
        """
        return self.send(
            notification_type=notification_type,
            intent=NotificationIntent.OPERATIONAL,
            autonomy_context=autonomy_context,
            title=title,
            message=message,
            source=source,
            **kwargs,
        )

    def send_info(
        self,
        notification_type: Union[str, NotificationType],
        autonomy_context: AutonomyContext,
        title: str,
        message: str,
        source: str,
        **kwargs,
    ) -> Optional[str]:
        """
        Convenience method for INFORMATIONAL intent notifications.

        BEST_EFFORT delivery - may fail silently.
        """
        return self.send(
            notification_type=notification_type,
            intent=NotificationIntent.INFORMATIONAL,
            autonomy_context=autonomy_context,
            title=title,
            message=message,
            source=source,
            **kwargs,
        )


# Singleton instance for convenience
_sdk_instance: Optional[NotificationSDK] = None


def get_sdk() -> NotificationSDK:
    """Get singleton SDK instance"""
    global _sdk_instance
    if _sdk_instance is None:
        _sdk_instance = NotificationSDK()
    return _sdk_instance


# Convenience function
def send_notification(
    notification_type: Union[str, NotificationType],
    intent: NotificationIntent,
    autonomy_context: AutonomyContext,
    title: str,
    message: str,
    source: str,
    **kwargs,
) -> Optional[str]:
    """
    Quick send using singleton SDK.

    Usage:
        from src.notification.sdk import send_notification, NotificationIntent, AutonomyContext, AutonomyMode

        ctx = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=agent_id,
        )

        # Operational notification (BEST_EFFORT)
        send_notification(
            "execution.slippage",
            NotificationIntent.OPERATIONAL,
            ctx,
            "Slippage Alert",
            "Average slippage 25.5 bps",
            "execution_alerts",
        )

        # Safety notification with irreversible action (GUARANTEED + PagerDuty + require_ack)
        send_notification(
            "safety.kill_switch",
            NotificationIntent.SAFETY,
            ctx,
            "KILL SWITCH ACTIVATED",
            "Trading halted",
            "autonomy_controller",
            irreversible=True,
        )
    """
    return get_sdk().send(
        notification_type=notification_type,
        intent=intent,
        autonomy_context=autonomy_context,
        title=title,
        message=message,
        source=source,
        **kwargs,
    )
```

### 3.3 Service (`src/notification/service.py`)

> **Implementation Note (2026-02-10):** In the production implementation, this module provides async delivery orchestration via `process_and_deliver()`, called directly from FastAPI routes -- not from RQ workers. The `deliver()` function signature and RQ retry semantics shown below are from the design phase. The core delivery logic (deduplication, rate limiting, adapter dispatch, safety-path strictness) is accurate.

```python
"""
Notification Service - Core delivery logic with safety-path strictness

v1.2: Added acknowledgment timeout scheduling, autonomy context logging

This module is called by RQ workers to process notifications.

Safety-path strictness:
- GUARANTEED delivery: Failures raise exceptions, trigger escalation
- BEST_EFFORT delivery: Failures logged, may be swallowed
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List

from src.common.logging import get_logger
from src.notification.models import (
    AckStatus,
    AutonomyContext,
    AutonomyMode,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    Notification,
    NotificationIntent,
    NotificationResult,
)

logger = get_logger(__name__)


def deliver(notification_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main entry point for RQ workers.

    Safety-path strictness:
    - GUARANTEED: Failures raise to trigger RQ retry, eventual DLQ + escalation
    - BEST_EFFORT: Partial failures accepted, full failure logged but may not retry

    v1.2: Schedules ack timeout job if require_ack=True

    Args:
        notification_data: Serialized Notification dict

    Returns:
        Serialized NotificationResult dict

    Raises:
        DeliveryFailedException: For GUARANTEED mode when all channels fail
        GuaranteedDeliveryEscalation: When GUARANTEED retries exhausted
    """
    notification = Notification.model_validate(notification_data)

    logger.info(
        "Processing notification",
        notification_id=str(notification.notification_id),
        notification_type=notification.notification_type.value,
        intent=notification.intent.value,
        delivery_mode=notification.delivery_mode.value,
        irreversible=notification.irreversible,
        autonomy_mode=notification.autonomy_context.autonomy_mode.value,
        require_ack=notification.require_ack,
    )

    # Phase 2: Check deduplication
    from src.notification.deduplication import should_deduplicate
    if should_deduplicate(notification):
        logger.info(
            "Notification deduplicated",
            notification_id=str(notification.notification_id),
            dedup_key=notification.dedup_key,
        )
        result = NotificationResult(
            notification_id=notification.notification_id,
            status=DeliveryStatus.DEDUPLICATED,
            channels_attempted=[],
            channels_succeeded=[],
            channels_failed=[],
        )
        _log_audit(notification, result)
        return result.model_dump(mode="json")

    # Phase 2: Check rate limits
    from src.notification.rate_limiting import acquire_rate_limit
    rate_limited_channels = []
    for channel in notification.channels:
        if not acquire_rate_limit(channel):
            rate_limited_channels.append(channel)

    # Remove rate-limited channels (they'll be retried)
    channels_to_deliver = [
        c for c in notification.channels
        if c not in rate_limited_channels
    ]

    if not channels_to_deliver and rate_limited_channels:
        # All channels rate limited - requeue
        raise RateLimitedException(
            f"All channels rate limited: {rate_limited_channels}"
        )

    # ================================================================
    # DELIVERY STRATEGY (per team feedback + func spec §12.1)
    # ================================================================
    # - WebSocket: Always fire-and-forget (real-time UI, not guaranteed)
    # - GUARANTEED: Sequential fallback (Slack → Email → PagerDuty)
    #              Stop on FIRST success to minimize human disruption
    # - BEST_EFFORT: Parallel delivery (failures acceptable)
    # ================================================================

    succeeded: List[Channel] = []
    failed: List[Channel] = []
    failure_reason = None

    # Step 1: WebSocket always attempted first (fire-and-forget for real-time UI)
    if Channel.WEBSOCKET in channels_to_deliver:
        try:
            _deliver_to_channel(notification, Channel.WEBSOCKET)
            succeeded.append(Channel.WEBSOCKET)
        except Exception as e:
            # WebSocket failure is NOT fatal - it's ephemeral by design
            logger.debug(
                "WebSocket delivery failed (non-fatal)",
                notification_id=str(notification.notification_id),
                error=str(e),
            )
        # Remove from further processing
        channels_to_deliver = [c for c in channels_to_deliver if c != Channel.WEBSOCKET]

    # Step 2: Deliver to remaining channels based on delivery mode
    if notification.delivery_mode == DeliveryMode.GUARANTEED:
        # GUARANTEED: Sequential fallback - stop on FIRST success
        # Order: Slack (fast) → Email (persistent) → PagerDuty (escalation)
        fallback_order = [Channel.SLACK, Channel.EMAIL, Channel.PAGERDUTY]

        for channel in fallback_order:
            if channel not in channels_to_deliver:
                continue
            try:
                _deliver_to_channel(notification, channel)
                succeeded.append(channel)
                logger.info(
                    "GUARANTEED delivery succeeded",
                    channel=channel.value,
                    notification_id=str(notification.notification_id),
                )
                break  # Stop on first success - don't escalate unnecessarily
            except Exception as e:
                failed.append(channel)
                failure_reason = str(e)
                logger.warning(
                    "GUARANTEED channel failed, trying next fallback",
                    channel=channel.value,
                    notification_id=str(notification.notification_id),
                    error=str(e),
                )
                continue  # Try next channel in fallback order
    else:
        # BEST_EFFORT: Parallel delivery - try all channels
        for channel in channels_to_deliver:
            try:
                _deliver_to_channel(notification, channel)
                succeeded.append(channel)
            except Exception as e:
                failed.append(channel)
                failure_reason = str(e)
                logger.warning(
                    "BEST_EFFORT channel failed",
                    channel=channel.value,
                    notification_id=str(notification.notification_id),
                    error=str(e),
                )

    # Determine overall status
    # For GUARANTEED: need at least one non-WebSocket success
    # For BEST_EFFORT: any success counts (including WebSocket-only)
    non_websocket_succeeded = [c for c in succeeded if c != Channel.WEBSOCKET]

    if notification.delivery_mode == DeliveryMode.GUARANTEED:
        # GUARANTEED requires at least one persistent channel to succeed
        if non_websocket_succeeded:
            status = DeliveryStatus.DELIVERED
        else:
            status = DeliveryStatus.FAILED
    else:
        # BEST_EFFORT: any delivery counts
        if succeeded:
            status = DeliveryStatus.DELIVERED
        else:
            status = DeliveryStatus.FAILED

    # Calculate ack timeout if require_ack
    ack_timeout_at = None
    if notification.require_ack and status == DeliveryStatus.DELIVERED:
        ack_timeout_at = datetime.utcnow() + timedelta(minutes=notification.ack_timeout_minutes)
        # Schedule ack timeout job
        _schedule_ack_timeout(notification, ack_timeout_at)

    result = NotificationResult(
        notification_id=notification.notification_id,
        status=status,
        channels_attempted=channels_to_deliver,
        channels_succeeded=succeeded,
        channels_failed=failed,
        failure_reason=failure_reason,
        delivered_at=datetime.utcnow() if succeeded else None,
        require_ack=notification.require_ack,
        ack_status=AckStatus.PENDING if notification.require_ack else None,
        ack_timeout_at=ack_timeout_at,
    )

    # Log to audit table
    _log_audit(notification, result)

    # Safety-path strictness: GUARANTEED vs BEST_EFFORT failure handling
    if status == DeliveryStatus.FAILED:
        if notification.delivery_mode == DeliveryMode.GUARANTEED:
            # GUARANTEED: Always raise to trigger RQ retry
            logger.error(
                "GUARANTEED delivery failed - triggering retry",
                notification_id=str(notification.notification_id),
                intent=notification.intent.value,
                failure_reason=failure_reason,
            )
            raise DeliveryFailedException(
                f"GUARANTEED delivery failed: {failure_reason}"
            )
        else:
            # BEST_EFFORT: Log but don't raise (no retry)
            logger.warning(
                "BEST_EFFORT delivery failed - not retrying",
                notification_id=str(notification.notification_id),
                intent=notification.intent.value,
                failure_reason=failure_reason,
            )

    return result.model_dump(mode="json")


def deliver_direct(notification_data: Dict[str, Any]) -> None:
    """
    Direct delivery without queue (fallback for failures).

    Used when Redis/RQ is unavailable for HIGH priority.
    """
    notification = Notification.model_validate(notification_data)

    for channel in notification.channels:
        try:
            _deliver_to_channel(notification, channel)
        except Exception as e:
            logger.error(
                "Direct delivery failed",
                channel=channel.value,
                error=str(e),
            )


def _deliver_to_channel(notification: Notification, channel: Channel) -> None:
    """Deliver notification to a specific channel"""
    from src.notification.adapters import get_adapter

    adapter = get_adapter(channel)
    adapter.deliver(notification)


def _schedule_ack_timeout(notification: Notification, timeout_at: datetime) -> None:
    """
    Schedule a job to check for ack timeout.

    If ack hasn't been received by timeout_at, the job will:
    - Update ack_status to TIMED_OUT
    - Re-escalate to PagerDuty (for SAFETY)
    - Emit ack_timeout event for agent learning
    """
    from rq import Queue
    from src.db.dependencies import create_redis

    redis = create_redis()
    queue = Queue("notify:ack_timeout", connection=redis)

    # Calculate delay in seconds
    delay_seconds = (timeout_at - datetime.utcnow()).total_seconds()

    # Handle edge case: timeout already passed (clock skew, race condition)
    if delay_seconds < 0:
        logger.warning(
            "Ack timeout already in past, scheduling immediate check",
            notification_id=str(notification.notification_id),
            timeout_at=timeout_at.isoformat(),
            delay_seconds=delay_seconds,
        )

    job = queue.enqueue_in(
        timedelta(seconds=max(delay_seconds, 0)),
        "src.notification.acknowledgment.check_ack_timeout",
        str(notification.notification_id),
        notification.intent.value,
        notification.autonomy_context.model_dump(mode="json"),
        job_timeout=60,
    )

    logger.info(
        "Scheduled ack timeout check",
        notification_id=str(notification.notification_id),
        timeout_at=timeout_at.isoformat(),
        job_id=job.id,
    )


def _log_audit(notification: Notification, result: NotificationResult) -> None:
    """Log notification to audit table with full autonomy context"""
    logger.info(
        "Notification audit",
        notification_id=str(notification.notification_id),
        notification_type=notification.notification_type.value,
        intent=notification.intent.value,
        autonomy_mode=notification.autonomy_context.autonomy_mode.value,
        agent_id=str(notification.autonomy_context.agent_id),
        decision_snapshot_id=str(notification.autonomy_context.decision_snapshot_id)
            if notification.autonomy_context.decision_snapshot_id else None,
        require_ack=notification.require_ack,
        status=result.status.value,
        channels_succeeded=[c.value for c in result.channels_succeeded],
        channels_failed=[c.value for c in result.channels_failed],
    )
    # Phase 2: Persist to notification_audit table


class RateLimitedException(Exception):
    """Raised when all channels are rate limited"""
    pass


class DeliveryFailedException(Exception):
    """Raised when delivery fails to all channels"""
    pass


class GuaranteedDeliveryEscalation(Exception):
    """
    Raised when GUARANTEED delivery exhausts all retries.

    This triggers DLQ escalation - human must be notified that
    a critical notification could not be delivered.
    """
    pass


def handle_dlq_escalation(job_id: str, notification_data: Dict[str, Any]) -> None:
    """
    Handle DLQ escalation for failed GUARANTEED notifications.

    Called by RQ failure handler when job exhausts retries.
    For GUARANTEED delivery, this MUST page on-call.

    INVARIANT per func spec §12.4:
        GUARANTEED = delivered OR escalated OR visible system degradation
        NOT infinite retry loops.

    DLQ visibility rules:
    - DLQ depth > 0 for SAFETY/GOVERNANCE → System health = DEGRADED
    - Health degradation surfaces via /health endpoint + monitoring
    - One OPERATIONAL alert per DLQ batch, not per item (avoid alert storms)

    If PagerDuty escalation also fails, system health degrades further
    and operators will see this via standard health monitoring.
    """
    notification = Notification.model_validate(notification_data)

    if notification.delivery_mode == DeliveryMode.GUARANTEED:
        logger.critical(
            "GUARANTEED notification in DLQ - triggering emergency escalation",
            notification_id=str(notification.notification_id),
            notification_type=notification.notification_type.value,
            intent=notification.intent.value,
            autonomy_mode=notification.autonomy_context.autonomy_mode.value,
        )

        # Emergency escalation: Direct PagerDuty call (bypasses normal flow)
        from src.notification.adapters.pagerduty import PagerDutyAdapter
        try:
            escalation_notification = Notification(
                notification_type=notification.notification_type,
                intent=NotificationIntent.SAFETY,
                delivery_mode=DeliveryMode.GUARANTEED,
                irreversible=True,
                autonomy_context=notification.autonomy_context,  # Preserve context
                title=f"[DLQ ESCALATION] {notification.title}",
                message=f"CRITICAL: Notification delivery failed after retries.\n\n"
                        f"Original: {notification.message}\n\n"
                        f"Job ID: {job_id}",
                source="uns.dlq_handler",
                metadata={
                    "original_notification_id": str(notification.notification_id),
                    "original_source": notification.source,
                },
            )
            PagerDutyAdapter().deliver(escalation_notification)
        except Exception as e:
            # If PagerDuty also fails, this is a critical system failure
            logger.critical(
                "DLQ escalation to PagerDuty failed - MANUAL INTERVENTION REQUIRED",
                error=str(e),
                notification_id=str(notification.notification_id),
            )
```

### 3.4 Adapters

#### Base Adapter (`src/notification/adapters/base.py`)

```python
"""
Base Adapter Interface

All channel adapters must implement this interface.
"""

from abc import ABC, abstractmethod

from src.notification.models import Notification


class BaseAdapter(ABC):
    """Abstract base class for notification adapters"""

    @abstractmethod
    def deliver(self, notification: Notification) -> None:
        """
        Deliver notification to channel.

        Args:
            notification: Notification to deliver

        Raises:
            Exception: If delivery fails
        """
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """
        Check if channel is healthy.

        Returns:
            True if channel is available
        """
        pass
```

#### Slack Adapter (`src/notification/adapters/slack.py`)

```python
"""
Slack Adapter - Webhook delivery

Extracted from src/execution/alerts.py
"""

import os
from typing import Dict, Any

import requests

from src.common.logging import get_logger
from src.notification.adapters.base import BaseAdapter
from src.notification.models import Notification, Priority

logger = get_logger(__name__)


class SlackAdapter(BaseAdapter):
    """Slack webhook adapter"""

    # Emoji by priority
    PRIORITY_EMOJI = {
        Priority.HIGH: ":rotating_light:",
        Priority.NORMAL: ":warning:",
        Priority.LOW: ":information_source:",
    }

    def __init__(self, webhook_url: str = None):
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        if not self.webhook_url:
            logger.warning("SLACK_WEBHOOK_URL not configured")

    def deliver(self, notification: Notification) -> None:
        """Send notification to Slack"""
        if not self.webhook_url:
            raise ValueError("Slack webhook URL not configured")

        payload = self._build_payload(notification)

        response = requests.post(
            self.webhook_url,
            json=payload,
            timeout=10,
        )

        if response.status_code != 200:
            raise Exception(
                f"Slack API error: {response.status_code} - {response.text}"
            )

        logger.debug(
            "Slack notification sent",
            notification_id=str(notification.notification_id),
        )

    def health_check(self) -> bool:
        """Check if Slack is configured"""
        return bool(self.webhook_url)

    def _build_payload(self, notification: Notification) -> Dict[str, Any]:
        """Build Slack Block Kit payload"""
        emoji = self.PRIORITY_EMOJI.get(notification.priority, ":bell:")

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {notification.title}",
                    "emoji": True,
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": notification.message,
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Type:* {notification.notification_type.value} | "
                               f"*Priority:* {notification.priority.value} | "
                               f"*Source:* {notification.source}",
                    }
                ]
            },
        ]

        # Add metadata fields if present
        if notification.metadata:
            fields = []
            for key, value in list(notification.metadata.items())[:10]:
                fields.append({
                    "type": "mrkdwn",
                    "text": f"*{key}:* {value}",
                })

            if fields:
                blocks.append({
                    "type": "section",
                    "fields": fields[:10],  # Slack limit
                })

        return {"blocks": blocks}
```

#### Email Adapter (`src/notification/adapters/email.py`)

```python
"""
Email Adapter - SMTP delivery

Extracted from src/execution/alerts.py
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.common.logging import get_logger
from src.notification.adapters.base import BaseAdapter
from src.notification.models import Notification, Priority

logger = get_logger(__name__)


class EmailAdapter(BaseAdapter):
    """SMTP email adapter"""

    def __init__(
        self,
        smtp_host: str = None,
        smtp_port: int = None,
        smtp_user: str = None,
        smtp_password: str = None,
        from_address: str = None,
        to_addresses: list = None,
    ):
        self.smtp_host = smtp_host or os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = smtp_port or int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = smtp_user or os.getenv("SMTP_USER")
        self.smtp_password = smtp_password or os.getenv("SMTP_PASSWORD")
        self.from_address = from_address or os.getenv("EMAIL_FROM")
        self.to_addresses = to_addresses or os.getenv("EMAIL_TO", "").split(",")

    def deliver(self, notification: Notification) -> None:
        """Send notification via email"""
        if not all([self.smtp_user, self.smtp_password, self.from_address]):
            raise ValueError("Email not fully configured")

        if not self.to_addresses or not self.to_addresses[0]:
            raise ValueError("No email recipients configured")

        msg = self._build_message(notification)

        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            server.send_message(msg)

        logger.debug(
            "Email notification sent",
            notification_id=str(notification.notification_id),
            recipients=self.to_addresses,
        )

    def health_check(self) -> bool:
        """Check if email is configured"""
        return bool(self.smtp_user and self.smtp_password)

    def _build_message(self, notification: Notification) -> MIMEMultipart:
        """Build email message"""
        msg = MIMEMultipart("alternative")

        # Subject with priority indicator
        priority_prefix = {
            Priority.HIGH: "[CRITICAL]",
            Priority.NORMAL: "[ALERT]",
            Priority.LOW: "[INFO]",
        }
        prefix = priority_prefix.get(notification.priority, "[ALERT]")
        msg["Subject"] = f"{prefix} {notification.title}"
        msg["From"] = self.from_address
        msg["To"] = ", ".join(self.to_addresses)

        # Plain text version
        plain_text = f"""
{notification.title}

{notification.message}

---
Type: {notification.notification_type.value}
Priority: {notification.priority.value}
Source: {notification.source}
Time: {notification.created_at.isoformat()}
"""

        # HTML version
        html = f"""
<html>
<body>
<h2>{notification.title}</h2>
<p>{notification.message}</p>
<hr>
<p style="color: gray; font-size: 12px;">
Type: {notification.notification_type.value} |
Priority: {notification.priority.value} |
Source: {notification.source} |
Time: {notification.created_at.isoformat()}
</p>
</body>
</html>
"""

        msg.attach(MIMEText(plain_text, "plain"))
        msg.attach(MIMEText(html, "html"))

        return msg
```

#### WebSocket Adapter (`src/notification/adapters/websocket.py`)

```python
"""
WebSocket Adapter - Real-time UI notifications

Uses existing AtpConnectionManager from routes_websocket_atp.py
"""

import asyncio
import threading
import time
from typing import Optional

from src.common.logging import get_logger
from src.notification.adapters.base import BaseAdapter
from src.notification.models import Notification

logger = get_logger(__name__)


class WebSocketAdapter(BaseAdapter):
    """
    WebSocket broadcast adapter - the "cognitive stream".

    WebSocket shows what humans should notice NOW, not history/audit.
    Intent determines visual treatment in the UI.

    Async/Sync Bridge:
    This adapter is called from sync RQ worker context but needs to
    broadcast to async WebSocket connections. We use a dedicated
    broadcast thread with its own event loop to handle this safely.
    """

    # Module-level event loop for WebSocket broadcasts
    # Initialized lazily on first use
    _broadcast_loop: Optional[asyncio.AbstractEventLoop] = None
    _broadcast_thread: Optional[threading.Thread] = None
    _loop_lock = threading.Lock()

    @classmethod
    def _ensure_broadcast_loop(cls) -> asyncio.AbstractEventLoop:
        """
        Ensure a dedicated event loop exists for WebSocket broadcasts.

        This creates a background thread with its own event loop,
        avoiding the fragile asyncio.get_event_loop() dance.
        """
        with cls._loop_lock:
            if cls._broadcast_loop is None or not cls._broadcast_loop.is_running():
                cls._broadcast_loop = asyncio.new_event_loop()

                def run_loop():
                    asyncio.set_event_loop(cls._broadcast_loop)
                    cls._broadcast_loop.run_forever()

                cls._broadcast_thread = threading.Thread(
                    target=run_loop,
                    daemon=True,
                    name="uns-websocket-broadcast",
                )
                cls._broadcast_thread.start()

                # Wait for loop to start
                while not cls._broadcast_loop.is_running():
                    time.sleep(0.01)

            return cls._broadcast_loop

    def deliver(self, notification: Notification) -> None:
        """Broadcast notification to all connected WebSocket clients"""
        from src.mcp_server.routes_websocket_atp import atp_connection_manager

        if not atp_connection_manager.active_connections:
            logger.debug("No WebSocket clients connected, skipping")
            return

        # Build message matching existing ATP WebSocket protocol
        # Include intent for UI to determine visual treatment
        message = {
            "type": "notification",
            "data": {
                "notification_id": str(notification.notification_id),
                "notification_type": notification.notification_type.value,
                "intent": notification.intent.value,  # UI uses for styling
                "delivery_mode": notification.delivery_mode.value,
                "irreversible": notification.irreversible,  # UI highlights
                "priority": notification.priority.value,
                "title": notification.title,
                "message": notification.message,
                "metadata": notification.metadata,
                "source": notification.source,
                "created_at": notification.created_at.isoformat(),
                # v1.2: Include ack info for SAFETY/GOVERNANCE
                "require_ack": notification.require_ack,
                "ack_status": notification.ack_status.value if notification.ack_status else None,
            }
        }

        # Use dedicated broadcast loop for thread-safe async execution
        loop = self._ensure_broadcast_loop()

        async def broadcast():
            try:
                await atp_connection_manager.broadcast(message)
            except Exception as e:
                logger.warning(
                    "WebSocket broadcast failed",
                    notification_id=str(notification.notification_id),
                    error=str(e),
                )

        # Schedule broadcast on dedicated loop (thread-safe)
        future = asyncio.run_coroutine_threadsafe(broadcast(), loop)

        # Fire-and-forget: don't wait for result
        # WebSocket delivery failure is not fatal per func spec §1.4
        # But log if it fails within a short timeout
        try:
            future.result(timeout=1.0)  # 1 second max wait
        except TimeoutError:
            logger.debug(
                "WebSocket broadcast timed out (fire-and-forget)",
                notification_id=str(notification.notification_id),
            )
        except Exception as e:
            logger.debug(
                "WebSocket broadcast error (fire-and-forget)",
                notification_id=str(notification.notification_id),
                error=str(e),
            )

        logger.debug(
            "WebSocket notification broadcast",
            notification_id=str(notification.notification_id),
            client_count=len(atp_connection_manager.active_connections),
        )

    def health_check(self) -> bool:
        """WebSocket is always available (fire and forget)"""
        return True
```

#### Adapter Factory (`src/notification/adapters/__init__.py`)

```python
"""
Adapter Factory

Provides adapter instances by channel type.
"""

from src.notification.models import Channel
from src.notification.adapters.base import BaseAdapter
from src.notification.adapters.slack import SlackAdapter
from src.notification.adapters.email import EmailAdapter
from src.notification.adapters.websocket import WebSocketAdapter


# Singleton adapter instances
_adapters: dict[Channel, BaseAdapter] = {}


def get_adapter(channel: Channel) -> BaseAdapter:
    """
    Get adapter instance for channel.

    Args:
        channel: Target channel

    Returns:
        Adapter instance

    Raises:
        ValueError: If channel not supported
    """
    if channel not in _adapters:
        _adapters[channel] = _create_adapter(channel)

    return _adapters[channel]


def _create_adapter(channel: Channel) -> BaseAdapter:
    """Create adapter instance"""
    if channel == Channel.SLACK:
        return SlackAdapter()
    elif channel == Channel.EMAIL:
        return EmailAdapter()
    elif channel == Channel.WEBSOCKET:
        return WebSocketAdapter()
    elif channel == Channel.PAGERDUTY:
        # Phase 3
        from src.notification.adapters.pagerduty import PagerDutyAdapter
        return PagerDutyAdapter()
    else:
        raise ValueError(f"Unsupported channel: {channel}")
```

---

## 4. Phase 2: Reliability

### 4.1 Deduplication (`src/notification/deduplication.py`)

```python
"""
Deduplication - Cognitive safety through duplicate suppression

Deduplication protects HUMAN ATTENTION, not just system performance.
The goal is to prevent alert fatigue while ensuring critical information
reaches operators without being lost in noise.

Uses Redis SETNX with TTL for atomic deduplication.
"""

from typing import Optional

from src.common.logging import get_logger
from src.db.dependencies import create_redis
from src.notification.models import Notification, Priority

logger = get_logger(__name__)

# Dedup windows by priority (seconds)
DEDUP_WINDOWS = {
    Priority.HIGH: 60,      # 1 minute
    Priority.NORMAL: 300,   # 5 minutes
    Priority.LOW: 1800,     # 30 minutes
}

# Key prefix
DEDUP_KEY_PREFIX = "uns:dedup:"


def should_deduplicate(notification: Notification) -> bool:
    """
    Check if notification should be deduplicated.

    Uses Redis SETNX - if key exists, it's a duplicate.

    **Idempotency Guarantee:** UNS guarantees idempotent handling for notifications
    with the same `notification_id` or `dedup_key` within the dedup window.
    Producers can safely retry notifications without creating duplicates.

    Args:
        notification: Notification to check

    Returns:
        True if should be deduplicated (is duplicate)
    """
    if not notification.dedup_key:
        return False

    redis = create_redis()
    key = f"{DEDUP_KEY_PREFIX}{notification.dedup_key}"
    window = DEDUP_WINDOWS.get(notification.priority, 300)

    # SETNX returns True if key was set (not duplicate)
    # Returns False if key exists (is duplicate)
    is_new = redis.set(key, "1", nx=True, ex=window)

    if not is_new:
        # Increment counter for summary pulse
        count_key = f"{key}:count"
        count = redis.incr(count_key)
        redis.expire(count_key, window)

        logger.debug(
            "Duplicate notification suppressed",
            dedup_key=notification.dedup_key,
            duplicate_count=count,
        )

        # Phase 2 enhancement: Send summary pulse after N duplicates
        if count == 5:
            _send_summary_pulse(notification, count)

    return not is_new


def _send_summary_pulse(notification: Notification, count: int) -> None:
    """
    Send summary notification for suppressed duplicates.

    LOOP PREVENTION (per team feedback):
    1. Summary notifications use INFORMATIONAL intent (never GUARANTEED)
    2. Summary notifications are sent directly, not queued (avoid latency)
    3. Summary notifications have their own dedup key (prevent summary-of-summary)
    4. Summary notifications skip deduplication check entirely (see below)
    """
    from src.notification.models import NotificationType
    from src.notification.adapters import get_adapter

    # Build summary notification - WebSocket only (cognitive stream)
    summary = Notification(
        notification_type=NotificationType("system.dedup_summary"),
        intent=NotificationIntent.INFORMATIONAL,  # Never GUARANTEED
        delivery_mode=DeliveryMode.BEST_EFFORT,   # Can fail silently
        priority=Priority.LOW,
        title=f"[Summary] {count} duplicate notifications suppressed",
        message=f"Suppressed {count} '{notification.notification_type.value}' "
                f"notifications in dedup window. Original: {notification.title}",
        source="uns.deduplication",
        channels=[Channel.WEBSOCKET],  # WebSocket only - no Slack spam
        autonomy_context=notification.autonomy_context,  # Preserve context
        # Special dedup key that's different from originals
        dedup_key=f"summary:{notification.dedup_key}:{count // 5}",
        metadata={
            "original_notification_type": notification.notification_type.value,
            "suppressed_count": count,
            "is_summary": True,  # Flag to skip dedup in future
        },
    )

    # Direct delivery to WebSocket only (no queue, no dedup check)
    # This avoids the loop: summary -> queue -> dedup check -> summary
    try:
        adapter = get_adapter(Channel.WEBSOCKET)
        adapter.deliver(summary)
        logger.debug(
            "Summary pulse sent",
            original_dedup_key=notification.dedup_key,
            suppressed_count=count,
        )
    except Exception as e:
        # Summary failure is not critical
        logger.debug(
            "Summary pulse failed (non-fatal)",
            error=str(e),
        )
```

### 4.2 Rate Limiting (`src/notification/rate_limiting.py`)

```python
"""
Rate Limiting - Token bucket implementation

Prevents channel throttling (e.g., Slack 1 req/sec).
"""

import time
from typing import Dict

from src.common.logging import get_logger
from src.db.dependencies import create_redis
from src.notification.models import Channel

logger = get_logger(__name__)

# Rate limits by channel (requests per second)
RATE_LIMITS: Dict[Channel, float] = {
    Channel.SLACK: 1.0,       # Slack webhook limit
    Channel.EMAIL: 10.0,      # SMTP is fast
    Channel.WEBSOCKET: 100.0, # Internal, generous limit
    Channel.PAGERDUTY: 5.0,   # PagerDuty limit
}

# Bucket capacity (burst allowance)
BUCKET_CAPACITY: Dict[Channel, int] = {
    Channel.SLACK: 5,       # Allow 5-message burst
    Channel.EMAIL: 20,
    Channel.WEBSOCKET: 50,
    Channel.PAGERDUTY: 10,
}

# Key prefix
RATE_LIMIT_PREFIX = "uns:ratelimit:"


def acquire_rate_limit(channel: Channel) -> bool:
    """
    Attempt to acquire rate limit token.

    Uses token bucket algorithm implemented in Redis.

    Args:
        channel: Channel to check

    Returns:
        True if token acquired (can proceed)
        False if rate limited (should wait/retry)
    """
    redis = create_redis()
    key = f"{RATE_LIMIT_PREFIX}{channel.value}"

    rate = RATE_LIMITS.get(channel, 10.0)
    capacity = BUCKET_CAPACITY.get(channel, 10)

    # Lua script for atomic token bucket
    lua_script = """
    local key = KEYS[1]
    local rate = tonumber(ARGV[1])
    local capacity = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])

    local bucket = redis.call('HMGET', key, 'tokens', 'last_update')
    local tokens = tonumber(bucket[1]) or capacity
    local last_update = tonumber(bucket[2]) or now

    -- Refill tokens based on time elapsed
    local elapsed = now - last_update
    local refill = elapsed * rate
    tokens = math.min(capacity, tokens + refill)

    -- Try to consume a token
    if tokens >= 1 then
        tokens = tokens - 1
        redis.call('HMSET', key, 'tokens', tokens, 'last_update', now)
        redis.call('EXPIRE', key, 60)
        return 1
    else
        redis.call('HMSET', key, 'tokens', tokens, 'last_update', now)
        redis.call('EXPIRE', key, 60)
        return 0
    end
    """

    result = redis.eval(lua_script, 1, key, rate, capacity, time.time())

    if not result:
        logger.debug(
            "Rate limit hit",
            channel=channel.value,
        )

    return bool(result)


def get_rate_limit_status(channel: Channel) -> Dict:
    """Get current rate limit status for channel"""
    redis = create_redis()
    key = f"{RATE_LIMIT_PREFIX}{channel.value}"

    bucket = redis.hgetall(key)

    return {
        "channel": channel.value,
        "tokens": float(bucket.get(b"tokens", BUCKET_CAPACITY.get(channel, 10))),
        "capacity": BUCKET_CAPACITY.get(channel, 10),
        "rate_per_second": RATE_LIMITS.get(channel, 10.0),
    }
```

### 4.3 Audit Logging (Database Model)

Add to `src/db/models.py`:

```python
class NotificationAuditModel(Base):
    """
    Notification audit log.

    Records all notifications for compliance and debugging.
    """
    __tablename__ = "notification_audit"
    __table_args__ = {"schema": "atp"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    notification_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    notification_type = Column(String(100), nullable=False, index=True)
    priority = Column(String(20), nullable=False)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    metadata = Column(JSONB, default={})

    # Routing
    channels_requested = Column(ARRAY(String), nullable=False)
    channels_succeeded = Column(ARRAY(String), default=[])
    channels_failed = Column(ARRAY(String), default=[])

    # Status
    status = Column(String(20), nullable=False, index=True)
    failure_reason = Column(Text)
    retry_count = Column(Integer, default=0)

    # Deduplication
    dedup_key = Column(String(64), index=True)

    # Source tracking
    source = Column(String(100), nullable=False, index=True)
    correlation_id = Column(String(100), index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, index=True)
    delivered_at = Column(DateTime(timezone=True))
    logged_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
```

### 4.4 Migration

Create `src/database/migrations/YYYYMMDD_notification_audit.sql`:

```sql
-- Notification audit table (v1.2: added autonomy and acknowledgment fields)
CREATE TABLE IF NOT EXISTS atp.notification_audit (
    id BIGSERIAL PRIMARY KEY,
    notification_id UUID NOT NULL,
    notification_type VARCHAR(100) NOT NULL,
    intent VARCHAR(20) NOT NULL,         -- SAFETY, GOVERNANCE, OPERATIONAL, INFORMATIONAL
    delivery_mode VARCHAR(20) NOT NULL,  -- GUARANTEED, BEST_EFFORT
    irreversible BOOLEAN DEFAULT FALSE,
    priority VARCHAR(20) NOT NULL,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',

    -- Autonomy context (v1.2)
    autonomy_mode VARCHAR(20) NOT NULL,  -- PREVIEW, SHADOW, LIVE
    agent_id UUID NOT NULL,
    plan_id UUID,
    decision_snapshot_id UUID,           -- Link to Why Layer
    execution_snapshot_id UUID,
    skip_snapshot_id UUID,

    -- Channel delivery
    channels_requested VARCHAR[] NOT NULL,
    channels_succeeded VARCHAR[] DEFAULT '{}',
    channels_failed VARCHAR[] DEFAULT '{}',

    status VARCHAR(20) NOT NULL,
    failure_reason TEXT,
    retry_count INTEGER DEFAULT 0,
    escalated_to VARCHAR(20),            -- Channel escalated to (if any)

    -- Acknowledgment (v1.2)
    require_ack BOOLEAN DEFAULT FALSE,
    ack_timeout_minutes INTEGER,
    ack_status VARCHAR(20),              -- PENDING, ACKED, DISMISSED, TIMED_OUT
    acked_at TIMESTAMPTZ,
    acked_by VARCHAR(255),

    dedup_key VARCHAR(64),
    source VARCHAR(100) NOT NULL,
    correlation_id VARCHAR(100),

    created_at TIMESTAMPTZ NOT NULL,
    delivered_at TIMESTAMPTZ,
    logged_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Indexes for common queries
CREATE INDEX idx_notification_audit_notification_id ON atp.notification_audit(notification_id);
CREATE INDEX idx_notification_audit_type ON atp.notification_audit(notification_type);
CREATE INDEX idx_notification_audit_intent ON atp.notification_audit(intent);
CREATE INDEX idx_notification_audit_status ON atp.notification_audit(status);
CREATE INDEX idx_notification_audit_source ON atp.notification_audit(source);
CREATE INDEX idx_notification_audit_created_at ON atp.notification_audit(created_at);
CREATE INDEX idx_notification_audit_dedup_key ON atp.notification_audit(dedup_key);
CREATE INDEX idx_notification_audit_autonomy_mode ON atp.notification_audit(autonomy_mode);
CREATE INDEX idx_notification_audit_agent_id ON atp.notification_audit(agent_id);
CREATE INDEX idx_notification_audit_ack_status ON atp.notification_audit(ack_status);
CREATE INDEX idx_notification_audit_require_ack_pending ON atp.notification_audit(require_ack, ack_status)
    WHERE require_ack = TRUE AND ack_status = 'PENDING';

-- Notification policies table (v2.1 — see migration 053_notification_policy.sql)
-- NOTE: The schema below is the original v1.2 design. The actual implementation
-- uses a different schema with JSONB columns for mode-specific overrides, version
-- chain support, and content-hash deduplication. See the migration file for the
-- current DDL.
--
-- Actual table: atp.notification_policy (singular)
-- Key differences from design:
--   - policy_id UUID PK (not VARCHAR id)
--   - channels, channels_escalation, delivery_mode_by_autonomy, require_ack are JSONB
--   - content_hash VARCHAR(64) for dedup (replaces config_hash)
--   - previous_version_id UUID for version chain
--   - activated_at, retired_at timestamps
--   - Partial unique index: one ACTIVE/PREVIEW per notification_type
CREATE TABLE IF NOT EXISTS atp.notification_policy (
    policy_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    notification_type VARCHAR(100) NOT NULL,
    version VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    delivery_mode VARCHAR(20) NOT NULL DEFAULT 'BEST_EFFORT',
    delivery_mode_by_autonomy JSONB DEFAULT '{}',
    channels JSONB DEFAULT '{}',
    channels_escalation JSONB DEFAULT '{}',
    escalation_trigger VARCHAR(20) DEFAULT 'ON_FAILURE',
    require_ack JSONB DEFAULT '{}',
    dedup_window_seconds INTEGER DEFAULT 300,
    rate_limit_per_minute INTEGER,
    description TEXT DEFAULT '',
    created_by VARCHAR(255),
    content_hash VARCHAR(64) NOT NULL,
    previous_version_id UUID REFERENCES atp.notification_policy(policy_id),
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    activated_at TIMESTAMPTZ,
    retired_at TIMESTAMPTZ
);

CREATE INDEX idx_notification_policy_type ON atp.notification_policy(notification_type);
CREATE INDEX idx_notification_policy_status ON atp.notification_policy(status);
CREATE INDEX idx_notification_policy_hash ON atp.notification_policy(content_hash);
CREATE UNIQUE INDEX idx_notification_policy_active_unique
    ON atp.notification_policy(notification_type, status)
    WHERE status IN ('ACTIVE', 'PREVIEW');

-- =============================================================================
-- PARTITIONING STRATEGY (Phase 4, optional for large-scale deployments)
-- =============================================================================
-- Consider partitioning notification_audit by created_at for:
-- 1. Faster retention cleanup (drop old partitions vs DELETE)
-- 2. Improved query performance for time-bounded queries
-- 3. Easier backup/restore of recent data
--
-- Example implementation (requires recreating table):
--
--     CREATE TABLE atp.notification_audit (
--         ...
--     ) PARTITION BY RANGE (created_at);
--
--     CREATE TABLE atp.notification_audit_2026_01
--         PARTITION OF atp.notification_audit
--         FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
--
-- Recommendation: Implement partitioning when notification_audit exceeds
-- 10M rows OR 90-day retention policy requires efficient cleanup.
-- =============================================================================

COMMENT ON TABLE atp.notification_audit IS 'Audit log for all notifications sent through UNS';
COMMENT ON TABLE atp.notification_policy IS 'Declarative notification behavior configuration (v2.1: JSONB columns, version chain, content-hash dedup)';
```

### 4.5 Acknowledgment Module (`src/notification/acknowledgment.py`)

```python
"""
Acknowledgment Module - Human confirmation handling

v1.2: Implements acknowledgment workflow for SAFETY/GOVERNANCE notifications

Handles:
- Recording acknowledgments (ACKED, DISMISSED)
- Timeout detection and escalation
- Emitting ack events for agent learning
"""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from src.common.logging import get_logger
from src.notification.models import (
    AckEvent,
    AckStatus,
    AutonomyContext,
    NotificationIntent,
)

logger = get_logger(__name__)


async def acknowledge_notification(
    notification_id: UUID,
    ack_status: AckStatus,
    acked_by: str,
) -> AckEvent:
    """
    Record acknowledgment for a notification.

    Args:
        notification_id: ID of the notification to acknowledge
        ack_status: ACKED or DISMISSED
        acked_by: Resolvable identity per func spec §5.5:
            - WebSocket: user@example.com (from JWT)
            - Slack: slack:U12345ABC or resolved email
            - PagerDuty: pagerduty:oncall@service-name
            If identity cannot be resolved to internal user, preserve
            qualified external identifier. Never record "unknown".

    Returns:
        AckEvent for audit/agent learning

    Raises:
        NotificationNotFoundError: If notification doesn't exist
        AlreadyAcknowledgedError: If already acked/dismissed/timed_out
    """
    from src.db.database import get_db

    async with get_db() as db:
        # Get notification from audit table
        result = await db.execute(
            """
            SELECT notification_id, intent, autonomy_mode, agent_id, plan_id,
                   decision_snapshot_id, require_ack, ack_status, delivered_at
            FROM atp.notification_audit
            WHERE notification_id = :notification_id
            """,
            {"notification_id": str(notification_id)},
        )
        row = result.fetchone()

        if not row:
            raise NotificationNotFoundError(f"Notification {notification_id} not found")

        if not row.require_ack:
            raise AckNotRequiredError(f"Notification {notification_id} does not require ack")

        if row.ack_status and row.ack_status != AckStatus.PENDING.value:
            raise AlreadyAcknowledgedError(
                f"Notification {notification_id} already {row.ack_status}"
            )

        # Calculate response time
        response_time_seconds = None
        if row.delivered_at:
            response_time_seconds = int(
                (datetime.utcnow() - row.delivered_at).total_seconds()
            )

        # Update notification
        await db.execute(
            """
            UPDATE atp.notification_audit
            SET ack_status = :ack_status,
                acked_at = :acked_at,
                acked_by = :acked_by
            WHERE notification_id = :notification_id
            """,
            {
                "notification_id": str(notification_id),
                "ack_status": ack_status.value,
                "acked_at": datetime.utcnow(),
                "acked_by": acked_by,
            },
        )
        await db.commit()

        # Build autonomy context from row
        autonomy_context = AutonomyContext(
            autonomy_mode=row.autonomy_mode,
            agent_id=UUID(row.agent_id),
            plan_id=UUID(row.plan_id) if row.plan_id else None,
            decision_snapshot_id=UUID(row.decision_snapshot_id)
                if row.decision_snapshot_id else None,
        )

        # Create ack event
        ack_event = AckEvent(
            notification_id=notification_id,
            ack_status=ack_status,
            acked_by=acked_by,
            response_time_seconds=response_time_seconds,
            autonomy_context=autonomy_context,
            intent=NotificationIntent(row.intent),
        )

        # Emit ack event for agent learning
        _emit_ack_event(ack_event)

        logger.info(
            "Notification acknowledged",
            notification_id=str(notification_id),
            ack_status=ack_status.value,
            acked_by=acked_by,
            response_time_seconds=response_time_seconds,
        )

        return ack_event


def check_ack_timeout(
    notification_id: str,
    intent: str,
    autonomy_context_data: Dict[str, Any],
) -> None:
    """
    Check if notification ack has timed out. Called by scheduled RQ job.

    If ack hasn't been received:
    - Update ack_status to TIMED_OUT
    - Re-escalate to PagerDuty (for SAFETY)
    - Emit ack_timeout event for agent learning
    """
    import asyncio

    async def _check():
        from src.db.database import get_db

        async with get_db() as db:
            # Get current ack status
            result = await db.execute(
                """
                SELECT ack_status, title, message, source
                FROM atp.notification_audit
                WHERE notification_id = :notification_id
                """,
                {"notification_id": notification_id},
            )
            row = result.fetchone()

            if not row:
                logger.warning(
                    "Ack timeout check: notification not found",
                    notification_id=notification_id,
                )
                return

            if row.ack_status != AckStatus.PENDING.value:
                # Already acked/dismissed, no action needed
                logger.debug(
                    "Ack timeout check: already processed",
                    notification_id=notification_id,
                    ack_status=row.ack_status,
                )
                return

            # Update to TIMED_OUT
            await db.execute(
                """
                UPDATE atp.notification_audit
                SET ack_status = :ack_status
                WHERE notification_id = :notification_id
                """,
                {
                    "notification_id": notification_id,
                    "ack_status": AckStatus.TIMED_OUT.value,
                },
            )
            await db.commit()

            logger.warning(
                "Notification ack timed out",
                notification_id=notification_id,
                intent=intent,
            )

            # Re-escalate for SAFETY intent
            if intent == NotificationIntent.SAFETY.value:
                _escalate_timeout(
                    notification_id,
                    row.title,
                    row.message,
                    autonomy_context_data,
                )

            # Emit timeout event for agent learning
            autonomy_context = AutonomyContext.model_validate(autonomy_context_data)
            ack_event = AckEvent(
                notification_id=UUID(notification_id),
                ack_status=AckStatus.TIMED_OUT,
                autonomy_context=autonomy_context,
                intent=NotificationIntent(intent),
            )
            _emit_ack_event(ack_event)

    asyncio.run(_check())


def _escalate_timeout(
    notification_id: str,
    title: str,
    message: str,
    autonomy_context_data: Dict[str, Any],
) -> None:
    """Re-escalate timed-out SAFETY notification to PagerDuty"""
    from src.notification.adapters.pagerduty import PagerDutyAdapter
    from src.notification.models import (
        AutonomyContext,
        DeliveryMode,
        Notification,
        NotificationIntent,
        NotificationType,
    )

    autonomy_context = AutonomyContext.model_validate(autonomy_context_data)

    escalation = Notification(
        notification_type=NotificationType.SYSTEM_ACK_TIMEOUT,
        intent=NotificationIntent.SAFETY,
        delivery_mode=DeliveryMode.GUARANTEED,
        irreversible=True,
        autonomy_context=autonomy_context,
        title=f"[ACK TIMEOUT] {title}",
        message=f"SAFETY notification was not acknowledged within timeout.\n\n"
                f"Original: {message}\n\n"
                f"Notification ID: {notification_id}",
        source="uns.ack_timeout",
        metadata={"original_notification_id": notification_id},
    )

    try:
        PagerDutyAdapter().deliver(escalation)
        logger.info(
            "Ack timeout escalated to PagerDuty",
            notification_id=notification_id,
        )
    except Exception as e:
        logger.critical(
            "Failed to escalate ack timeout to PagerDuty",
            notification_id=notification_id,
            error=str(e),
        )


def _emit_ack_event(ack_event: AckEvent) -> None:
    """
    Emit acknowledgment event for:
    - Audit trail
    - Agent learning
    - Governance enforcement
    - Trust calibration

    **Human Trust Calibration Note:** Acknowledgment patterns may be used to
    adjust autonomy levels over time (e.g., if humans consistently dismiss
    certain notification types, reduce their frequency or change routing).
    However, this calibration must never occur in real-time execution loops.
    Trust adjustments are policy-level changes that require review and
    deployment, not runtime behavior modifications.
    """
    # Log for audit
    logger.info(
        "Ack event emitted",
        notification_id=str(ack_event.notification_id),
        ack_status=ack_event.ack_status.value,
        acked_by=ack_event.acked_by,
        response_time_seconds=ack_event.response_time_seconds,
        autonomy_mode=ack_event.autonomy_context.autonomy_mode.value,
        intent=ack_event.intent.value,
    )

    # Future: Publish to event bus for agent learning
    # Future: Update trust calibration metrics


class NotificationNotFoundError(Exception):
    """Notification not found in audit table"""
    pass


class AckNotRequiredError(Exception):
    """Notification does not require acknowledgment"""
    pass


class AlreadyAcknowledgedError(Exception):
    """Notification has already been acknowledged"""
    pass
```

### 4.6 Notification Policies (`src/notification/policies.py`)

> **Implementation Note (v2.1):** The code below reflects the original design-phase
> specification. The actual implementation uses a `@dataclass`-based `NotificationPolicy`
> (not Pydantic `BaseModel`) with the following additions:
>
> - **Full lifecycle:** `PolicyService.preview_policy()`, `activate_policy()`, `retire_policy()`
> - **Version chain:** `previous_version_id: Optional[UUID]` links policy versions
> - **DB persistence:** `NotificationPolicyModel` ORM model (migration `053_notification_policy.sql`)
> - **Hot-reload:** `PolicyRegistry.reload_from_database()` + `POST /api/v1/policies/reload` endpoint
> - **YAML loader:** `policy_loader.py` with `load_policy_from_yaml()`, `compute_policy_content_hash()`
> - **P0 fields:** `delivery_mode_by_autonomy`, `channels_escalation`, `escalation_trigger`
> - **MIP-225:** Producer hooks no longer pass `channels=` or `delivery_mode=` to `sdk.send()`
> - **6 default policies** registered at startup (safety, governance, execution, circuit breaker)
>
> See `src/notification/policies.py` for the current implementation.

```python
"""
Notification Policies - Declarative behavior configuration

v1.2: YAML-based policies for notification behavior

Policies are:
- Versioned and hashed for audit
- Mode-specific (different behavior per PREVIEW/SHADOW/LIVE)
- Stored in database with ACTIVE state for runtime use
"""

import hashlib
from typing import Any, Dict, List, Optional
from uuid import UUID

import yaml
from pydantic import BaseModel, Field

from src.common.logging import get_logger
from src.notification.models import (
    AckStatus,
    AutonomyMode,
    Channel,
    DeliveryMode,
    NotificationIntent,
)

logger = get_logger(__name__)


class AutonomyModeOverride(BaseModel):
    """Mode-specific policy overrides"""
    channels: Optional[List[Channel]] = None
    require_ack: Optional[bool] = None
    ack_timeout_minutes: Optional[int] = None


class SlackFormat(BaseModel):
    """Slack-specific formatting options"""
    emoji: str = "📢"
    color: str = "#0066cc"
    include_ack_button: bool = False


class NotificationPolicy(BaseModel):
    """
    Declarative notification policy.

    Defines behavior for a notification type, with mode-specific overrides.
    """
    id: str = Field(..., description="Unique policy ID (e.g., 'safety.kill_switch')")
    version: int = Field(default=1)
    intent: NotificationIntent
    delivery_mode: DeliveryMode
    channels: List[Channel]
    require_ack: bool = False
    ack_timeout_minutes: int = 15
    block_autonomy_until_ack: bool = Field(
        default=False,
        description=(
            "If True, block autonomy state TRANSITIONS until ack. "
            "CRITICAL per func spec §6.3: May only pause STATE TRANSITIONS "
            "(PREVIEW→SHADOW, policy activation), NEVER execution loops "
            "(trade cycles, order routing). UNS is control plane only. "
            "EXPLICITLY FORBIDDEN: This flag may never gate:\n"
            "- In-flight execution\n"
            "- Order placement\n"
            "- Risk unwind logic\n"
            "These are data-plane operations that must remain autonomous."
        ),
    )
    dedup_window_seconds: int = 60
    include_decision_snapshot: bool = True

    # Mode-specific overrides
    autonomy_mode_overrides: Dict[AutonomyMode, AutonomyModeOverride] = Field(
        default_factory=dict
    )

    # Slack formatting
    slack_format: SlackFormat = Field(default_factory=SlackFormat)

    def get_channels_for_mode(self, mode: AutonomyMode) -> List[Channel]:
        """Get channels for a specific autonomy mode"""
        if mode in self.autonomy_mode_overrides:
            override = self.autonomy_mode_overrides[mode]
            if override.channels is not None:
                return override.channels
        return self.channels

    def get_require_ack_for_mode(self, mode: AutonomyMode) -> bool:
        """Get require_ack for a specific autonomy mode"""
        if mode in self.autonomy_mode_overrides:
            override = self.autonomy_mode_overrides[mode]
            if override.require_ack is not None:
                return override.require_ack
        return self.require_ack

    def compute_hash(self) -> str:
        """Compute hash for audit trail"""
        content = self.model_dump_json(exclude={"version"})
        return hashlib.sha256(content.encode()).hexdigest()[:16]


class PolicyRegistry:
    """
    Registry for notification policies with hot-reload support.

    Loads policies from database (ACTIVE state) and provides
    lookup by notification type.

    Hot-reload: Policies are cached with a TTL. When cache is stale,
    next access triggers a background refresh. No worker restart needed.

    Initialization Pattern:
    -----------------------
    The registry should be initialized at application startup:

        # In app startup (async context)
        registry = get_policy_registry()
        await registry.load()  # Trigger initial load

    SDK Behavior:
    -------------
    The SDK calls get_sync() which returns cached policies without
    triggering refresh (since SDK.send() is synchronous). If called
    before initial load, get_sync() returns None and SDK falls back
    to built-in defaults. This is intentional:

    - Sync context cannot block on async DB call
    - SDK defaults are safe fallbacks
    - Async contexts (API routes) use get() which refreshes

    Thread Safety Notes:
    --------------------
    - _is_cache_stale() reads _last_refresh_at without lock (stale reads acceptable)
    - _refresh_lock prevents thundering herd on cache miss
    - _policies dict swap is atomic (single assignment)
    """

    # Default cache TTL: 60 seconds
    # Policies update within this window after database change
    DEFAULT_CACHE_TTL_SECONDS = 60

    def __init__(self, cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS):
        self._policies: Dict[str, NotificationPolicy] = {}
        self._loaded = False
        self._cache_ttl_seconds = cache_ttl_seconds
        self._last_refresh_at: Optional[datetime] = None
        self._refresh_lock = asyncio.Lock()

    def _is_cache_stale(self) -> bool:
        """Check if cache needs refresh"""
        if not self._loaded or self._last_refresh_at is None:
            return True
        age_seconds = (datetime.utcnow() - self._last_refresh_at).total_seconds()
        return age_seconds > self._cache_ttl_seconds

    async def _refresh_if_stale(self) -> None:
        """Refresh cache if stale (with lock to prevent thundering herd)"""
        if not self._is_cache_stale():
            return

        # Use lock to prevent multiple concurrent refreshes
        async with self._refresh_lock:
            # Double-check after acquiring lock
            if not self._is_cache_stale():
                return
            await self._load_from_database()

    async def _load_from_database(self) -> None:
        """Load all ACTIVE policies from database"""
        from src.db.database import get_db

        async with get_db() as db:
            result = await db.execute(
                """
                SELECT id, version, intent, delivery_mode, channels,
                       require_ack, ack_timeout_minutes, block_autonomy_until_ack,
                       dedup_window_seconds, include_decision_snapshot,
                       autonomy_mode_overrides, slack_format
                FROM atp.notification_policies
                WHERE state = 'ACTIVE'
                """
            )
            rows = result.fetchall()

            new_policies = {}
            for row in rows:
                policy = NotificationPolicy(
                    id=row.id,
                    version=row.version,
                    intent=NotificationIntent(row.intent),
                    delivery_mode=DeliveryMode(row.delivery_mode),
                    channels=[Channel(c) for c in row.channels],
                    require_ack=row.require_ack,
                    ack_timeout_minutes=row.ack_timeout_minutes,
                    block_autonomy_until_ack=row.block_autonomy_until_ack,
                    dedup_window_seconds=row.dedup_window_seconds,
                    include_decision_snapshot=row.include_decision_snapshot,
                    autonomy_mode_overrides=_parse_mode_overrides(
                        row.autonomy_mode_overrides
                    ),
                    slack_format=SlackFormat(**row.slack_format)
                        if row.slack_format else SlackFormat(),
                )
                new_policies[policy.id] = policy

            # Atomic swap
            self._policies = new_policies
            self._last_refresh_at = datetime.utcnow()
            self._loaded = True

            logger.info(
                "Refreshed notification policies",
                count=len(self._policies),
                cache_ttl_seconds=self._cache_ttl_seconds,
            )

    async def load(self) -> None:
        """Initial load (for backwards compatibility)"""
        await self._load_from_database()

    async def get(self, policy_id: str) -> Optional[NotificationPolicy]:
        """Get policy by ID (refreshes cache if stale)"""
        await self._refresh_if_stale()
        return self._policies.get(policy_id)

    async def get_for_notification_type(
        self, notification_type: str
    ) -> Optional[NotificationPolicy]:
        """Get policy for notification type (e.g., 'safety.kill_switch')"""
        return await self.get(notification_type)

    def get_sync(self, policy_id: str) -> Optional[NotificationPolicy]:
        """
        Synchronous get (for SDK use in sync context).

        WARNING: Does not trigger refresh. Use async get() in async contexts.
        Returns cached policy or None if not loaded.
        """
        if not self._loaded:
            logger.warning(
                "PolicyRegistry.get_sync called before initial load",
                policy_id=policy_id,
            )
            return None
        return self._policies.get(policy_id)


def _parse_mode_overrides(
    data: Optional[Dict[str, Any]]
) -> Dict[AutonomyMode, AutonomyModeOverride]:
    """Parse mode overrides from JSON"""
    if not data:
        return {}

    result = {}
    for mode_str, override_data in data.items():
        mode = AutonomyMode(mode_str)
        channels = None
        if "channels" in override_data:
            channels = [Channel(c) for c in override_data["channels"]]
        result[mode] = AutonomyModeOverride(
            channels=channels,
            require_ack=override_data.get("require_ack"),
            ack_timeout_minutes=override_data.get("ack_timeout_minutes"),
        )
    return result


def load_policy_from_yaml(yaml_content: str) -> NotificationPolicy:
    """
    Load a policy from YAML content.

    Example YAML:
        notification_policy:
          id: safety.kill_switch
          version: 1
          intent: SAFETY
          delivery_mode: GUARANTEED
          channels: [SLACK, WEBSOCKET, PAGERDUTY]
          require_ack: true
          ack_timeout_minutes: 15
          autonomy_mode_overrides:
            PREVIEW:
              channels: [WEBSOCKET]
              require_ack: false
    """
    data = yaml.safe_load(yaml_content)
    policy_data = data.get("notification_policy", data)

    # Parse enums
    policy_data["intent"] = NotificationIntent(policy_data["intent"])
    policy_data["delivery_mode"] = DeliveryMode(policy_data["delivery_mode"])
    policy_data["channels"] = [Channel(c) for c in policy_data["channels"]]

    # Parse mode overrides
    if "autonomy_mode_overrides" in policy_data:
        policy_data["autonomy_mode_overrides"] = _parse_mode_overrides(
            policy_data["autonomy_mode_overrides"]
        )

    # Parse slack format
    if "slack_format" in policy_data:
        policy_data["slack_format"] = SlackFormat(**policy_data["slack_format"])

    return NotificationPolicy(**policy_data)


# Singleton registry
_registry: Optional[PolicyRegistry] = None


async def get_policy_registry() -> PolicyRegistry:
    """Get singleton policy registry"""
    global _registry
    if _registry is None:
        _registry = PolicyRegistry()
        await _registry.load()
    return _registry
```

---

## 5. Phase 3: Integration

### 5.1 ExecutionAlerts Migration

Modify `src/execution/alerts.py`:

```python
# Before (direct delivery):
def send_slack_alert(message: str, severity: str = "warning"):
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    requests.post(webhook_url, json={"text": message})

# After (via UNS with intent + autonomy context):
from src.notification.sdk import send_notification, NotificationIntent
from src.notification.models import AutonomyContext, AutonomyMode, Channel

def send_slack_alert(
    message: str,
    severity: str = "warning",
    autonomy_context: AutonomyContext = None,
    agent_id: str = None,
):
    """Send alert via UNS with full autonomy context"""
    # Map severity to intent
    if severity == "critical":
        intent = NotificationIntent.SAFETY
    else:
        intent = NotificationIntent.OPERATIONAL

    # Build autonomy context if not provided
    if autonomy_context is None:
        from uuid import uuid4
        autonomy_context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,  # Default to LIVE for backwards compat
            agent_id=uuid4() if agent_id is None else agent_id,
        )

    send_notification(
        notification_type="execution.alert",
        intent=intent,
        autonomy_context=autonomy_context,  # v1.2: Required
        title=f"Execution Alert ({severity})",
        message=message,
        source="execution_alerts",
        # Channels derived from intent + autonomy_mode:
        # SAFETY + LIVE → [Slack, WebSocket, PagerDuty if irreversible]
        # OPERATIONAL + LIVE → [Slack]
        # OPERATIONAL + SHADOW → [WebSocket]
    )
```

### 5.2 Agent Governor Integration

Add to `src/services/agent_governor_service.py`:

```python
async def _notify_approval_required(
    self,
    contract: DecisionContract,
    autonomy_context: AutonomyContext,
) -> None:
    """
    Notify operators that approval is required (GOVERNANCE intent).

    v1.2: Includes autonomy context and decision_snapshot_id for Why Layer link.
    """
    from src.notification.sdk import send_notification, NotificationIntent
    from src.notification.models import AutonomyContext

    # Link to Why Layer if available
    decision_snapshot_id = getattr(contract, 'decision_snapshot_id', None)
    ctx = AutonomyContext(
        autonomy_mode=autonomy_context.autonomy_mode,
        agent_id=contract.agent_id,
        plan_id=getattr(contract, 'plan_id', None),
        decision_snapshot_id=decision_snapshot_id,
    )

    send_notification(
        notification_type="governance.approval_required",
        intent=NotificationIntent.GOVERNANCE,  # GUARANTEED delivery
        autonomy_context=ctx,  # v1.2: Required
        title=f"Approval Required: {contract.capability}",
        message=f"Agent '{contract.agent_id}' requests approval for "
                f"{contract.capability}. Contract: {contract.contract_id}",
        source="agent_governor",
        # channels derived from intent + autonomy_mode
        # LIVE → [Slack, WebSocket]
        # SHADOW → [Slack, WebSocket]
        # PREVIEW → [WebSocket]
        metadata={
            "contract_id": str(contract.contract_id),
            "capability": contract.capability,
            "agent_id": str(contract.agent_id),
            "decision_snapshot_id": str(decision_snapshot_id) if decision_snapshot_id else None,
        },
        correlation_id=str(contract.contract_id),
    )


async def _notify_autonomy_change(
    self,
    new_mode: str,
    previous_mode: str,
    triggered_by: str,
    agent_id: UUID,
) -> None:
    """
    Notify when autonomy mode changes (GOVERNANCE + irreversible).

    v1.2: Includes full autonomy context, require_ack for LIVE transitions.
    """
    from src.notification.sdk import send_notification, NotificationIntent
    from src.notification.models import AutonomyContext, AutonomyMode

    # Mode transitions to LIVE are irreversible (money at risk)
    is_irreversible = new_mode == "LIVE"

    ctx = AutonomyContext(
        autonomy_mode=AutonomyMode(new_mode),
        agent_id=agent_id,
    )

    send_notification(
        notification_type="governance.autonomy_change",
        intent=NotificationIntent.GOVERNANCE,
        autonomy_context=ctx,  # v1.2: Required
        title=f"Autonomy Mode: {previous_mode} → {new_mode}",
        message=f"Execution mode changed from {previous_mode} to {new_mode} "
                f"by {triggered_by}",
        source="agent_governor",
        irreversible=is_irreversible,  # Triggers PagerDuty if LIVE
        require_ack=is_irreversible,   # v1.2: Require ack for LIVE transitions
        metadata={
            "previous_mode": previous_mode,
            "new_mode": new_mode,
            "triggered_by": triggered_by,
        },
    )
```

### 5.3 PagerDuty Adapter (`src/notification/adapters/pagerduty.py`)

```python
"""
PagerDuty Adapter - On-call escalation

For HIGH priority notifications that need immediate attention.
"""

import os

import requests

from src.common.logging import get_logger
from src.notification.adapters.base import BaseAdapter
from src.notification.models import Notification

logger = get_logger(__name__)


class PagerDutyAdapter(BaseAdapter):
    """PagerDuty Events API v2 adapter"""

    EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"

    def __init__(self, routing_key: str = None):
        self.routing_key = routing_key or os.getenv("PAGERDUTY_ROUTING_KEY")

    def deliver(self, notification: Notification) -> None:
        """Trigger PagerDuty incident"""
        if not self.routing_key:
            raise ValueError("PagerDuty routing key not configured")

        payload = {
            "routing_key": self.routing_key,
            "event_action": "trigger",
            "dedup_key": notification.dedup_key,
            "payload": {
                "summary": notification.title,
                "severity": "critical",  # HIGH priority = critical
                "source": notification.source,
                "custom_details": {
                    "message": notification.message,
                    "notification_type": notification.notification_type.value,
                    "notification_id": str(notification.notification_id),
                    **notification.metadata,
                },
            },
        }

        response = requests.post(
            self.EVENTS_URL,
            json=payload,
            timeout=10,
        )

        if response.status_code != 202:
            raise Exception(
                f"PagerDuty API error: {response.status_code} - {response.text}"
            )

        logger.info(
            "PagerDuty incident triggered",
            notification_id=str(notification.notification_id),
            dedup_key=notification.dedup_key,
        )

    def health_check(self) -> bool:
        """Check if PagerDuty is configured"""
        return bool(self.routing_key)
```

### 5.4 WebSocket Reconnection Handler

When a user reconnects via WebSocket, they should see pending SAFETY/GOVERNANCE
notifications. This ensures awareness continuity — if a kill switch was activated
while they were disconnected, they need to know immediately on reconnect.

Add to `src/mcp_server/routes_websocket_atp.py`:

```python
"""
WebSocket Reconnection Handler for Pending Notifications

When a user connects, query for unacked SAFETY/GOVERNANCE notifications
and send them immediately. This ensures awareness continuity.
"""

from datetime import datetime, timedelta
from typing import List

from src.common.logging import get_logger
from src.notification.models import AckStatus, NotificationIntent

logger = get_logger(__name__)

# Maximum age for pending notifications to show on reconnect (24 hours)
PENDING_NOTIFICATION_MAX_AGE_HOURS = 24


async def get_pending_notifications_for_reconnect() -> List[dict]:
    """
    Get pending SAFETY/GOVERNANCE notifications for a reconnecting user.

    Returns notifications that:
    - Are SAFETY or GOVERNANCE intent
    - Require acknowledgment (require_ack = true)
    - Have not been acknowledged (ack_status = PENDING)
    - Were created within the last 24 hours

    These are sent to the user immediately on WebSocket connect.
    """
    from src.db.database import get_db

    cutoff = datetime.utcnow() - timedelta(hours=PENDING_NOTIFICATION_MAX_AGE_HOURS)

    async with get_db() as db:
        result = await db.execute(
            """
            SELECT
                notification_id,
                notification_type,
                intent,
                priority,
                title,
                message,
                metadata,
                source,
                created_at,
                delivered_at,
                require_ack,
                ack_status,
                ack_timeout_at
            FROM atp.notification_audit
            WHERE intent IN ('SAFETY', 'GOVERNANCE')
              AND require_ack = true
              AND ack_status = 'PENDING'
              AND created_at > :cutoff
            ORDER BY created_at DESC
            LIMIT 50
            """,
            {"cutoff": cutoff},
        )
        rows = result.fetchall()

        notifications = []
        for row in rows:
            notifications.append({
                "type": "pending_notification",
                "data": {
                    "notification_id": row.notification_id,
                    "notification_type": row.notification_type,
                    "intent": row.intent,
                    "priority": row.priority,
                    "title": row.title,
                    "message": row.message,
                    "metadata": row.metadata or {},
                    "source": row.source,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "require_ack": row.require_ack,
                    "ack_status": row.ack_status,
                    "ack_timeout_at": row.ack_timeout_at.isoformat() if row.ack_timeout_at else None,
                    "is_reconnect_replay": True,  # Flag so UI knows this is replay
                },
            })

        logger.info(
            "Retrieved pending notifications for reconnect",
            count=len(notifications),
        )

        return notifications


# -----------------------------------------------------------------------------
# PERFORMANCE NOTE: Reconnection Query Index
# -----------------------------------------------------------------------------
# The get_pending_notifications_for_reconnect() query should be supported by
# a partial composite index for optimal performance:
#
#     CREATE INDEX idx_notif_audit_reconnect
#     ON atp.notification_audit(intent, ack_status, created_at DESC)
#     WHERE require_ack = TRUE AND ack_status = 'PENDING';
#
# This partial index covers the common case (pending acks) without bloating
# the index with already-acknowledged notifications. Add to migration if
# reconnection query latency becomes a concern.
# -----------------------------------------------------------------------------


async def handle_websocket_connect(websocket, connection_id: str) -> None:
    """
    Handle WebSocket connection - send pending notifications.

    Call this after accepting the WebSocket connection but before
    entering the main message loop.
    """
    try:
        pending = await get_pending_notifications_for_reconnect()
        if pending:
            logger.info(
                "Sending pending notifications on reconnect",
                connection_id=connection_id,
                count=len(pending),
            )
            for notification in pending:
                await websocket.send_json(notification)
    except Exception as e:
        # Don't fail the connection for pending notification errors
        logger.warning(
            "Failed to send pending notifications on reconnect",
            connection_id=connection_id,
            error=str(e),
        )
```

Update the existing WebSocket connection handler to call this:

```python
# In ATP WebSocket handler (routes_websocket_atp.py)
@router.websocket("/ws/atp/{session_id}")
async def websocket_atp_endpoint(websocket: WebSocket, session_id: str):
    await atp_connection_manager.connect(websocket)
    connection_id = f"atp-{session_id}-{uuid4().hex[:8]}"

    try:
        # NEW: Send pending notifications immediately on connect
        await handle_websocket_connect(websocket, connection_id)

        # Existing message loop...
        while True:
            data = await websocket.receive_text()
            # ... handle messages
    except WebSocketDisconnect:
        atp_connection_manager.disconnect(websocket)
```

---

## 6. Configuration (`src/notification/config.py`)

```python
"""
UNS Configuration

All configuration via environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass
from typing import List


@dataclass
class UNSConfig:
    """Unified Notification Service configuration"""

    # Feature flags
    enabled: bool = True
    fallback_to_direct: bool = True  # Direct delivery if queue fails

    # Deduplication
    dedup_enabled: bool = True
    dedup_window_high: int = 60      # seconds
    dedup_window_normal: int = 300
    dedup_window_low: int = 1800

    # Rate limiting
    rate_limit_enabled: bool = True
    slack_rate_limit: float = 1.0    # requests per second
    email_rate_limit: float = 10.0
    pagerduty_rate_limit: float = 5.0

    # Retry
    max_retries: int = 3
    retry_backoff_base: int = 1      # seconds
    retry_backoff_max: int = 60

    # Audit
    audit_enabled: bool = True
    audit_retention_days: int = 90

    # Channels
    slack_webhook_url: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: List[str] = None
    pagerduty_routing_key: str = ""

    @classmethod
    def from_env(cls) -> "UNSConfig":
        """Load configuration from environment variables"""
        return cls(
            enabled=os.getenv("UNS_ENABLED", "true").lower() == "true",
            fallback_to_direct=os.getenv("UNS_FALLBACK_DIRECT", "true").lower() == "true",

            dedup_enabled=os.getenv("UNS_DEDUP_ENABLED", "true").lower() == "true",
            dedup_window_high=int(os.getenv("UNS_DEDUP_WINDOW_HIGH", "60")),
            dedup_window_normal=int(os.getenv("UNS_DEDUP_WINDOW_NORMAL", "300")),
            dedup_window_low=int(os.getenv("UNS_DEDUP_WINDOW_LOW", "1800")),

            rate_limit_enabled=os.getenv("UNS_RATE_LIMIT_ENABLED", "true").lower() == "true",

            max_retries=int(os.getenv("UNS_MAX_RETRIES", "3")),

            audit_enabled=os.getenv("UNS_AUDIT_ENABLED", "true").lower() == "true",
            audit_retention_days=int(os.getenv("UNS_AUDIT_RETENTION_DAYS", "90")),

            slack_webhook_url=os.getenv("SLACK_WEBHOOK_URL", ""),
            smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            smtp_user=os.getenv("SMTP_USER", ""),
            smtp_password=os.getenv("SMTP_PASSWORD", ""),
            email_from=os.getenv("EMAIL_FROM", ""),
            email_to=os.getenv("EMAIL_TO", "").split(",") if os.getenv("EMAIL_TO") else [],
            pagerduty_routing_key=os.getenv("PAGERDUTY_ROUTING_KEY", ""),
        )


# Singleton config instance
_config: UNSConfig = None


def get_config() -> UNSConfig:
    """Get UNS configuration"""
    global _config
    if _config is None:
        _config = UNSConfig.from_env()
    return _config
```

---

## 7. Worker Setup

> **Implementation Note (2026-02-10):** Sections 7.1 through 7.4 describe RQ worker configuration from the design phase. The production implementation does not use RQ workers. UNS runs as a standalone FastAPI application (`src/notification/main.py`) with async delivery orchestration. There are no separate worker processes, priority queues, or supervisor configs to manage. The DLQ escalation logic described in 7.3 is handled within the async delivery pipeline instead. This section is retained for design history.

### 7.1 RQ Worker Configuration

Add to worker startup script or supervisor config:

```bash
# Start UNS workers (one per priority for isolation)
rq worker notify:high --with-scheduler &
rq worker notify:normal --with-scheduler &
rq worker notify:low --with-scheduler &
```

### 7.2 Supervisor Configuration

```ini
[program:uns-worker-high]
command=rq worker notify:high --with-scheduler
directory=/app
autostart=true
autorestart=true
priority=10

[program:uns-worker-normal]
command=rq worker notify:normal --with-scheduler
directory=/app
autostart=true
autorestart=true
priority=20

[program:uns-worker-low]
command=rq worker notify:low --with-scheduler
directory=/app
autostart=true
autorestart=true
priority=30
```

### 7.3 RQ Failure Handler Registration

**Critical:** The `handle_dlq_escalation` function must be wired to RQ's exception handler.

Create `src/notification/worker.py`:

```python
"""
RQ Worker Configuration - Failure Handler Registration

CRITICAL: This module MUST be imported by the worker process to wire
DLQ escalation for failed GUARANTEED notifications.
"""

from rq import Worker
from rq.job import Job

from src.common.logging import get_logger
from src.notification.models import DeliveryMode, Notification
from src.notification.service import handle_dlq_escalation

logger = get_logger(__name__)


class UNSWorker(Worker):
    """
    Custom RQ worker with failure handler for DLQ escalation.

    Usage:
        rq worker notify:high --worker-class src.notification.worker.UNSWorker
    """

    def handle_job_failure(
        self,
        job: Job,
        exc_type,
        exc_value,
        traceback,
    ):
        """
        Handle job failure - escalate GUARANTEED notifications to DLQ handler.

        Called by RQ when a job exhausts all retries.
        """
        # Call parent handler first (logs failure, moves to failed queue)
        super().handle_job_failure(job, exc_type, exc_value, traceback)

        # Check if this is a notification delivery job
        if job.func_name == "src.notification.service.deliver":
            try:
                notification_data = job.args[0]
                notification = Notification.model_validate(notification_data)

                # Only escalate GUARANTEED notifications
                if notification.delivery_mode == DeliveryMode.GUARANTEED:
                    logger.warning(
                        "GUARANTEED notification failed - triggering DLQ escalation",
                        job_id=job.id,
                        notification_id=str(notification.notification_id),
                        intent=notification.intent.value,
                    )
                    handle_dlq_escalation(job.id, notification_data)
                else:
                    # BEST_EFFORT - log and continue
                    logger.info(
                        "BEST_EFFORT notification failed - no escalation",
                        job_id=job.id,
                        notification_id=str(notification.notification_id),
                    )
            except Exception as e:
                # Failure handler itself failed - critical error
                logger.critical(
                    "DLQ escalation handler failed - MANUAL INTERVENTION REQUIRED",
                    job_id=job.id,
                    error=str(e),
                )
```

Update supervisor config to use custom worker:

```ini
[program:uns-worker-high]
command=rq worker notify:high --with-scheduler --worker-class src.notification.worker.UNSWorker
directory=/app
autostart=true
autorestart=true
priority=10
```

### 7.4 Scheduler Requirement

> **CRITICAL:** The `--with-scheduler` flag is **required** for ack timeout jobs.

Without the scheduler:
- `enqueue_in()` jobs will not execute
- Ack timeouts will never fire
- SAFETY notifications may never re-escalate

Verify scheduler is running:
```bash
rq info --by-queue | grep -i scheduler
```

---

## 8. Testing Strategy

### 8.1 Unit Tests

```python
# tests/notification/test_sdk.py

import pytest
from unittest.mock import Mock, patch

from src.notification.sdk import NotificationSDK
from src.notification.models import (
    Channel,
    DeliveryMode,
    NotificationIntent,
    NotificationType,
    Priority,
)


class TestNotificationSDK:

    @patch("src.notification.sdk.create_redis")
    def test_send_queues_notification_with_intent(self, mock_redis):
        """Test that send() queues with intent-derived settings"""
        sdk = NotificationSDK()

        job_id = sdk.send(
            notification_type=NotificationType.SAFETY_KILL_SWITCH,
            intent=NotificationIntent.SAFETY,
            title="Test",
            message="Test message",
            source="test",
        )

        assert job_id is not None

    def test_intent_derives_priority(self):
        """Test that priority is derived from intent"""
        sdk = NotificationSDK()

        # SAFETY → HIGH
        # GOVERNANCE → HIGH
        # OPERATIONAL → NORMAL
        # INFORMATIONAL → LOW
        from src.notification.models import Notification

        safety_notif = Notification(
            notification_type=NotificationType.SAFETY_KILL_SWITCH,
            intent=NotificationIntent.SAFETY,
            title="Test",
            message="Test",
            source="test",
        )
        assert safety_notif.priority == Priority.HIGH

        info_notif = Notification(
            notification_type=NotificationType.SYSTEM_BACKTEST_COMPLETE,
            intent=NotificationIntent.INFORMATIONAL,
            title="Test",
            message="Test",
            source="test",
        )
        assert info_notif.priority == Priority.LOW

    def test_intent_derives_delivery_mode(self):
        """Test that delivery_mode is derived from intent"""
        from src.notification.models import Notification

        # SAFETY/GOVERNANCE → GUARANTEED
        safety_notif = Notification(
            notification_type=NotificationType.SAFETY_KILL_SWITCH,
            intent=NotificationIntent.SAFETY,
            title="Test",
            message="Test",
            source="test",
        )
        assert safety_notif.delivery_mode == DeliveryMode.GUARANTEED

        # OPERATIONAL/INFORMATIONAL → BEST_EFFORT
        op_notif = Notification(
            notification_type=NotificationType.EXECUTION_SLIPPAGE,
            intent=NotificationIntent.OPERATIONAL,
            title="Test",
            message="Test",
            source="test",
        )
        assert op_notif.delivery_mode == DeliveryMode.BEST_EFFORT

    def test_irreversible_adds_pagerduty(self):
        """Test that irreversible=True adds PagerDuty channel"""
        sdk = NotificationSDK()

        channels = sdk.DEFAULT_CHANNELS_BY_INTENT[NotificationIntent.SAFETY].copy()
        assert Channel.PAGERDUTY not in channels

        # With irreversible=True, PagerDuty should be added
        # (tested via notification creation, not direct channel check)

    def test_generate_dedup_key_deterministic(self):
        """Test that dedup keys are deterministic"""
        sdk = NotificationSDK()

        key1 = sdk._generate_dedup_key("type", "source", "message")
        key2 = sdk._generate_dedup_key("type", "source", "message")

        assert key1 == key2
```

### 8.2 Integration Tests

```python
# tests/notification/test_integration.py

import pytest
from src.notification.sdk import send_notification
from src.notification.models import DeliveryMode, NotificationIntent, NotificationType


@pytest.mark.integration
class TestNotificationIntegration:

    def test_end_to_end_slack_delivery(self, mock_slack_webhook):
        """Test full flow from SDK to Slack delivery"""
        job_id = send_notification(
            notification_type=NotificationType.EXECUTION_SLIPPAGE,
            intent=NotificationIntent.OPERATIONAL,
            title="Integration Test",
            message="This is a test notification",
            source="test_integration",
        )

        # Wait for job to complete
        # Assert Slack webhook was called
        assert mock_slack_webhook.called

    def test_guaranteed_delivery_raises_on_failure(self, mock_failing_slack):
        """Test that GUARANTEED delivery raises on failure"""
        with pytest.raises(RuntimeError, match="GUARANTEED"):
            send_notification(
                notification_type=NotificationType.SAFETY_KILL_SWITCH,
                intent=NotificationIntent.SAFETY,  # GUARANTEED
                title="Critical Test",
                message="This should raise on failure",
                source="test",
            )

    def test_best_effort_swallows_failure(self, mock_failing_slack):
        """Test that BEST_EFFORT delivery does not raise on failure"""
        # Should not raise, returns None
        result = send_notification(
            notification_type=NotificationType.SYSTEM_BACKTEST_COMPLETE,
            intent=NotificationIntent.INFORMATIONAL,  # BEST_EFFORT
            title="Info Test",
            message="This should not raise",
            source="test",
        )
        assert result is None

    def test_deduplication_protects_cognitive_load(self, redis_client):
        """Test that duplicate notifications are suppressed (cognitive safety)"""
        job1 = send_notification(
            notification_type=NotificationType.EXECUTION_SLIPPAGE,
            intent=NotificationIntent.OPERATIONAL,
            title="Duplicate Test",
            message="Same message",
            source="test",
            dedup_key="test-dedup-key",
        )

        job2 = send_notification(
            notification_type=NotificationType.EXECUTION_SLIPPAGE,
            intent=NotificationIntent.OPERATIONAL,
            title="Duplicate Test",
            message="Same message",
            source="test",
            dedup_key="test-dedup-key",
        )

        # Second should be deduplicated - protecting human attention
        # Check audit log for DEDUPLICATED status
```

### 8.3 GUARANTEED Delivery Test Matrix

> **Critical:** GUARANTEED delivery is safety-critical infrastructure. These tests MUST pass before any release.

The sequential fallback logic requires explicit test coverage for all edge cases:

```python
# tests/notification/test_guaranteed_delivery.py
"""
GUARANTEED Delivery Test Suite

Tests the sequential fallback chain: Slack → Email → PagerDuty
Each test verifies correct behavior at each fallback step.

Run with: pytest tests/notification/test_guaranteed_delivery.py -v
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.notification.models import (
    Channel,
    DeliveryMode,
    DeliveryStatus,
    Notification,
    NotificationIntent,
    NotificationType,
    AutonomyContext,
    AutonomyMode,
)
from src.notification.service import deliver


class TestGuaranteedDeliveryFallback:
    """Test the sequential fallback chain for GUARANTEED delivery"""

    @pytest.fixture
    def safety_notification(self):
        """Create a SAFETY notification (GUARANTEED delivery)"""
        return Notification(
            notification_type=NotificationType("safety.kill_switch"),
            intent=NotificationIntent.SAFETY,
            delivery_mode=DeliveryMode.GUARANTEED,
            autonomy_context=AutonomyContext(
                autonomy_mode=AutonomyMode.LIVE,
                agent_id="test-agent-001",
            ),
            title="Kill Switch Activated",
            message="Trading halted",
            source="test",
            channels=[Channel.SLACK, Channel.EMAIL, Channel.PAGERDUTY],
        )

    # ================================================================
    # HAPPY PATH TESTS
    # ================================================================

    @patch("src.notification.adapters.get_adapter")
    def test_slack_succeeds_stops_fallback(self, mock_get_adapter, safety_notification):
        """
        Scenario: Slack succeeds on first try
        Expected: Email and PagerDuty are NOT attempted
        """
        slack_adapter = Mock()
        email_adapter = Mock()
        pagerduty_adapter = Mock()

        def get_adapter_side_effect(channel):
            if channel == Channel.SLACK:
                return slack_adapter
            elif channel == Channel.EMAIL:
                return email_adapter
            elif channel == Channel.PAGERDUTY:
                return pagerduty_adapter
            return Mock()

        mock_get_adapter.side_effect = get_adapter_side_effect

        result = deliver(safety_notification.model_dump(mode="json"))

        # Slack was called and succeeded
        slack_adapter.deliver.assert_called_once()
        # Email and PagerDuty were NOT called (early exit on success)
        email_adapter.deliver.assert_not_called()
        pagerduty_adapter.deliver.assert_not_called()
        # Status is DELIVERED
        assert result["status"] == DeliveryStatus.DELIVERED.value

    # ================================================================
    # FALLBACK TESTS
    # ================================================================

    @patch("src.notification.adapters.get_adapter")
    def test_slack_fails_email_succeeds(self, mock_get_adapter, safety_notification):
        """
        Scenario: Slack fails, Email succeeds
        Expected: PagerDuty is NOT attempted
        """
        slack_adapter = Mock()
        slack_adapter.deliver.side_effect = Exception("Slack API error")
        email_adapter = Mock()
        pagerduty_adapter = Mock()

        def get_adapter_side_effect(channel):
            if channel == Channel.SLACK:
                return slack_adapter
            elif channel == Channel.EMAIL:
                return email_adapter
            elif channel == Channel.PAGERDUTY:
                return pagerduty_adapter
            return Mock()

        mock_get_adapter.side_effect = get_adapter_side_effect

        result = deliver(safety_notification.model_dump(mode="json"))

        # Slack was attempted and failed
        slack_adapter.deliver.assert_called_once()
        # Email was called and succeeded
        email_adapter.deliver.assert_called_once()
        # PagerDuty was NOT called (early exit on Email success)
        pagerduty_adapter.deliver.assert_not_called()
        # Status is DELIVERED (Email succeeded)
        assert result["status"] == DeliveryStatus.DELIVERED.value

    @patch("src.notification.adapters.get_adapter")
    def test_slack_email_fail_pagerduty_succeeds(self, mock_get_adapter, safety_notification):
        """
        Scenario: Slack fails, Email fails, PagerDuty succeeds
        Expected: All three attempted, final status DELIVERED
        """
        slack_adapter = Mock()
        slack_adapter.deliver.side_effect = Exception("Slack API error")
        email_adapter = Mock()
        email_adapter.deliver.side_effect = Exception("SMTP error")
        pagerduty_adapter = Mock()

        def get_adapter_side_effect(channel):
            if channel == Channel.SLACK:
                return slack_adapter
            elif channel == Channel.EMAIL:
                return email_adapter
            elif channel == Channel.PAGERDUTY:
                return pagerduty_adapter
            return Mock()

        mock_get_adapter.side_effect = get_adapter_side_effect

        result = deliver(safety_notification.model_dump(mode="json"))

        # All three were attempted
        slack_adapter.deliver.assert_called_once()
        email_adapter.deliver.assert_called_once()
        pagerduty_adapter.deliver.assert_called_once()
        # Status is DELIVERED (PagerDuty succeeded)
        assert result["status"] == DeliveryStatus.DELIVERED.value

    # ================================================================
    # FAILURE TESTS
    # ================================================================

    @patch("src.notification.adapters.get_adapter")
    def test_all_channels_fail_raises_exception(self, mock_get_adapter, safety_notification):
        """
        Scenario: All channels fail
        Expected: DeliveryFailedException raised (triggers RQ retry)
        """
        slack_adapter = Mock()
        slack_adapter.deliver.side_effect = Exception("Slack API error")
        email_adapter = Mock()
        email_adapter.deliver.side_effect = Exception("SMTP error")
        pagerduty_adapter = Mock()
        pagerduty_adapter.deliver.side_effect = Exception("PagerDuty API error")

        def get_adapter_side_effect(channel):
            if channel == Channel.SLACK:
                return slack_adapter
            elif channel == Channel.EMAIL:
                return email_adapter
            elif channel == Channel.PAGERDUTY:
                return pagerduty_adapter
            return Mock()

        mock_get_adapter.side_effect = get_adapter_side_effect

        from src.notification.service import DeliveryFailedException

        with pytest.raises(DeliveryFailedException):
            deliver(safety_notification.model_dump(mode="json"))

    # ================================================================
    # WEBSOCKET TESTS (Fire-and-Forget)
    # ================================================================

    @patch("src.notification.adapters.get_adapter")
    def test_websocket_failure_does_not_affect_guaranteed(self, mock_get_adapter, safety_notification):
        """
        Scenario: WebSocket fails, Slack succeeds
        Expected: GUARANTEED status is DELIVERED (WebSocket is fire-and-forget)
        """
        safety_notification.channels = [Channel.WEBSOCKET, Channel.SLACK]

        websocket_adapter = Mock()
        websocket_adapter.deliver.side_effect = Exception("WebSocket disconnected")
        slack_adapter = Mock()

        def get_adapter_side_effect(channel):
            if channel == Channel.WEBSOCKET:
                return websocket_adapter
            elif channel == Channel.SLACK:
                return slack_adapter
            return Mock()

        mock_get_adapter.side_effect = get_adapter_side_effect

        result = deliver(safety_notification.model_dump(mode="json"))

        # WebSocket failure is NOT fatal
        assert result["status"] == DeliveryStatus.DELIVERED.value

    @patch("src.notification.adapters.get_adapter")
    def test_websocket_only_guaranteed_fails(self, mock_get_adapter, safety_notification):
        """
        Scenario: Only WebSocket configured, WebSocket succeeds
        Expected: GUARANTEED fails (WebSocket alone cannot satisfy GUARANTEED)
        """
        safety_notification.channels = [Channel.WEBSOCKET]

        websocket_adapter = Mock()

        def get_adapter_side_effect(channel):
            if channel == Channel.WEBSOCKET:
                return websocket_adapter
            return Mock()

        mock_get_adapter.side_effect = get_adapter_side_effect

        from src.notification.service import DeliveryFailedException

        # GUARANTEED requires a persistent channel (not just WebSocket)
        with pytest.raises(DeliveryFailedException):
            deliver(safety_notification.model_dump(mode="json"))

    # ================================================================
    # PARTIAL CONFIGURATION TESTS
    # ================================================================

    @patch("src.notification.adapters.get_adapter")
    def test_only_pagerduty_configured(self, mock_get_adapter, safety_notification):
        """
        Scenario: Only PagerDuty is configured (Slack/Email not available)
        Expected: Goes directly to PagerDuty, succeeds
        """
        safety_notification.channels = [Channel.PAGERDUTY]

        pagerduty_adapter = Mock()

        def get_adapter_side_effect(channel):
            if channel == Channel.PAGERDUTY:
                return pagerduty_adapter
            return Mock()

        mock_get_adapter.side_effect = get_adapter_side_effect

        result = deliver(safety_notification.model_dump(mode="json"))

        pagerduty_adapter.deliver.assert_called_once()
        assert result["status"] == DeliveryStatus.DELIVERED.value

    # ================================================================
    # TIMEOUT TESTS
    # ================================================================

    @patch("src.notification.adapters.get_adapter")
    def test_channel_timeout_treated_as_failure(self, mock_get_adapter, safety_notification):
        """
        Scenario: Slack times out, Email succeeds
        Expected: Timeout is treated as failure, fallback to Email
        """
        import socket

        slack_adapter = Mock()
        slack_adapter.deliver.side_effect = socket.timeout("Connection timed out")
        email_adapter = Mock()

        def get_adapter_side_effect(channel):
            if channel == Channel.SLACK:
                return slack_adapter
            elif channel == Channel.EMAIL:
                return email_adapter
            return Mock()

        mock_get_adapter.side_effect = get_adapter_side_effect

        result = deliver(safety_notification.model_dump(mode="json"))

        # Timeout treated as failure, fell back to Email
        slack_adapter.deliver.assert_called_once()
        email_adapter.deliver.assert_called_once()
        assert result["status"] == DeliveryStatus.DELIVERED.value


class TestGuaranteedDeliveryAudit:
    """Test that GUARANTEED delivery creates proper audit trail"""

    @patch("src.notification.service._log_audit")
    @patch("src.notification.adapters.get_adapter")
    def test_audit_logs_successful_channel(self, mock_get_adapter, mock_log_audit):
        """Verify audit log records which channel succeeded"""
        notification = Notification(
            notification_type=NotificationType("safety.kill_switch"),
            intent=NotificationIntent.SAFETY,
            delivery_mode=DeliveryMode.GUARANTEED,
            autonomy_context=AutonomyContext(
                autonomy_mode=AutonomyMode.LIVE,
                agent_id="test-agent",
            ),
            title="Test",
            message="Test",
            source="test",
            channels=[Channel.SLACK],
        )

        slack_adapter = Mock()
        mock_get_adapter.return_value = slack_adapter

        deliver(notification.model_dump(mode="json"))

        # Verify audit was called with successful channel
        mock_log_audit.assert_called_once()
        audit_call = mock_log_audit.call_args
        result = audit_call[0][1]  # Second arg is NotificationResult
        assert Channel.SLACK in result.channels_succeeded

    @patch("src.notification.service._log_audit")
    @patch("src.notification.adapters.get_adapter")
    def test_audit_logs_failed_channels(self, mock_get_adapter, mock_log_audit):
        """Verify audit log records which channels failed before success"""
        notification = Notification(
            notification_type=NotificationType("safety.kill_switch"),
            intent=NotificationIntent.SAFETY,
            delivery_mode=DeliveryMode.GUARANTEED,
            autonomy_context=AutonomyContext(
                autonomy_mode=AutonomyMode.LIVE,
                agent_id="test-agent",
            ),
            title="Test",
            message="Test",
            source="test",
            channels=[Channel.SLACK, Channel.EMAIL],
        )

        slack_adapter = Mock()
        slack_adapter.deliver.side_effect = Exception("Slack failed")
        email_adapter = Mock()

        def get_adapter_side_effect(channel):
            if channel == Channel.SLACK:
                return slack_adapter
            elif channel == Channel.EMAIL:
                return email_adapter
            return Mock()

        mock_get_adapter.side_effect = get_adapter_side_effect

        deliver(notification.model_dump(mode="json"))

        # Verify audit records both failed and succeeded channels
        mock_log_audit.assert_called_once()
        audit_call = mock_log_audit.call_args
        result = audit_call[0][1]
        assert Channel.SLACK in result.channels_failed
        assert Channel.EMAIL in result.channels_succeeded


class TestPolicyOverrides:
    """Test that policies override SDK default channels"""

    @patch("src.notification.policies.get_policy_registry")
    @patch("src.notification.adapters.get_adapter")
    def test_policy_overrides_default_channels(
        self, mock_get_adapter, mock_get_registry
    ):
        """Policy channels should be used instead of SDK defaults"""
        # Create a policy that only uses EMAIL (not SDK default of SLACK)
        policy = NotificationPolicy(
            id="safety.kill_switch",
            version=1,
            intent=NotificationIntent.SAFETY,
            delivery_mode=DeliveryMode.GUARANTEED,
            channels=[Channel.EMAIL],  # Override: EMAIL only, not SLACK
            require_ack=True,
        )
        mock_registry = Mock()
        mock_registry.get_sync.return_value = policy
        mock_get_registry.return_value = mock_registry

        email_adapter = Mock()
        mock_get_adapter.return_value = email_adapter

        # SDK.send() without explicit channels - should use policy channels
        sdk = NotificationSDK()
        sdk.send(
            notification_type="safety.kill_switch",
            intent=NotificationIntent.SAFETY,
            autonomy_context=AutonomyContext(
                autonomy_mode=AutonomyMode.LIVE,
                agent_id="test-agent",
            ),
            title="Test",
            message="Test",
            source="test",
            # channels NOT specified - should come from policy
        )

        # Verify EMAIL adapter was called (from policy), not SLACK (SDK default)
        mock_get_adapter.assert_called_with(Channel.EMAIL)
        email_adapter.deliver.assert_called_once()


class TestModeDependentRouting:
    """Test autonomy mode affects channel routing"""

    @patch("src.notification.adapters.get_adapter")
    def test_preview_mode_websocket_only(self, mock_get_adapter):
        """PREVIEW mode should only use WebSocket, not Slack/Email"""
        ws_adapter = Mock()
        mock_get_adapter.return_value = ws_adapter

        notification = Notification(
            notification_type=NotificationType("operational.status_change"),
            intent=NotificationIntent.OPERATIONAL,
            delivery_mode=DeliveryMode.BEST_EFFORT,
            autonomy_context=AutonomyContext(
                autonomy_mode=AutonomyMode.PREVIEW,  # PREVIEW mode
                agent_id="test-agent",
            ),
            title="Test",
            message="Test",
            source="test",
            # channels NOT specified - should derive from mode
        )

        deliver(notification.model_dump(mode="json"))

        # In PREVIEW mode, only WebSocket should be attempted
        mock_get_adapter.assert_called_once_with(Channel.WEBSOCKET)

    @patch("src.notification.adapters.get_adapter")
    def test_live_mode_full_routing(self, mock_get_adapter):
        """LIVE mode with irreversible should include PagerDuty"""
        slack_adapter = Mock()
        pagerduty_adapter = Mock()

        def get_adapter_by_channel(channel):
            if channel == Channel.SLACK:
                return slack_adapter
            elif channel == Channel.PAGERDUTY:
                return pagerduty_adapter
            return Mock()

        mock_get_adapter.side_effect = get_adapter_by_channel

        notification = Notification(
            notification_type=NotificationType("safety.kill_switch"),
            intent=NotificationIntent.SAFETY,
            delivery_mode=DeliveryMode.GUARANTEED,
            irreversible=True,  # Should trigger PagerDuty
            autonomy_context=AutonomyContext(
                autonomy_mode=AutonomyMode.LIVE,  # LIVE mode
                agent_id="test-agent",
            ),
            title="Test",
            message="Test",
            source="test",
            # channels NOT specified - should include PagerDuty due to irreversible
        )

        deliver(notification.model_dump(mode="json"))

        # In LIVE mode with irreversible, PagerDuty should be in the channel list
        called_channels = [call[0][0] for call in mock_get_adapter.call_args_list]
        assert Channel.PAGERDUTY in called_channels
```

### 8.4 GUARANTEED Delivery Test Coverage Requirements

Before release, the following test matrix MUST pass:

| Scenario | Expected Behavior | Test Method |
|----------|-------------------|-------------|
| Slack succeeds | Stop, don't try Email/PagerDuty | `test_slack_succeeds_stops_fallback` |
| Slack fails, Email succeeds | Stop, don't try PagerDuty | `test_slack_fails_email_succeeds` |
| Slack+Email fail, PagerDuty succeeds | DELIVERED status | `test_slack_email_fail_pagerduty_succeeds` |
| All channels fail | `DeliveryFailedException` raised | `test_all_channels_fail_raises_exception` |
| WebSocket fails, Slack succeeds | DELIVERED (WebSocket is fire-and-forget) | `test_websocket_failure_does_not_affect_guaranteed` |
| Only WebSocket configured | Fails (WebSocket can't satisfy GUARANTEED) | `test_websocket_only_guaranteed_fails` |
| Channel timeout | Treated as failure, fallback continues | `test_channel_timeout_treated_as_failure` |
| Audit trail on success | Records successful channel | `test_audit_logs_successful_channel` |
| Audit trail on fallback | Records failed + successful channels | `test_audit_logs_failed_channels` |
| Policy overrides SDK defaults | Policy channels used instead of SDK defaults | `test_policy_overrides_default_channels` |
| Mode-dependent routing (PREVIEW) | WebSocket only, no Slack/Email | `test_preview_mode_websocket_only` |
| Mode-dependent routing (LIVE) | Full channel set + PagerDuty for irreversible | `test_live_mode_full_routing` |

### 8.5 Integration Test Checklist (Staging Environment)

Run these manually in staging before production deployment:

```bash
# 1. Test full fallback chain with real channels
./scripts/test_guaranteed_fallback.sh --env staging

# 2. Verify DLQ escalation
./scripts/test_dlq_escalation.sh --env staging

# 3. Verify ack timeout re-escalation
./scripts/test_ack_timeout.sh --env staging
```

**Staging test scenarios:**

- [ ] Kill switch notification reaches PagerDuty within 30 seconds
- [ ] If Slack is down, Email delivers within 60 seconds
- [ ] If all channels fail, DLQ escalation fires within 5 minutes
- [ ] Ack timeout (15 min) triggers re-escalation to PagerDuty
- [ ] WebSocket reconnect shows pending SAFETY notifications

---

## 9. Monitoring & Observability

### 9.1 Metrics to Track

| Metric | Type | Description |
|--------|------|-------------|
| `uns_notifications_queued_total` | Counter | Total notifications queued by priority |
| `uns_notifications_delivered_total` | Counter | Successful deliveries by channel |
| `uns_notifications_failed_total` | Counter | Failed deliveries by channel |
| `uns_notifications_deduplicated_total` | Counter | Deduplicated notifications |
| `uns_notifications_rate_limited_total` | Counter | Rate-limited notifications |
| `uns_delivery_latency_seconds` | Histogram | Time from queue to delivery |
| `uns_dlq_depth` | Gauge | Current DLQ size |

### 9.2 Health Endpoint

Add to API routes:

```python
@router.get("/v1/notifications/health")
async def notification_health():
    """UNS health check"""
    from src.notification.adapters import get_adapter
    from src.notification.models import Channel

    return {
        "status": "healthy",
        "channels": {
            "slack": get_adapter(Channel.SLACK).health_check(),
            "email": get_adapter(Channel.EMAIL).health_check(),
            "websocket": get_adapter(Channel.WEBSOCKET).health_check(),
            "pagerduty": get_adapter(Channel.PAGERDUTY).health_check(),
        },
        "queues": {
            "high": _get_queue_depth("notify:high"),
            "normal": _get_queue_depth("notify:normal"),
            "low": _get_queue_depth("notify:low"),
        },
        "dlq_depth": _get_failed_job_count(),
    }
```

---

## 10. UI Integration Guide

### 10.1 Overview

This section provides frontend developers with the specifications needed to integrate UNS notifications into the UI. The UI is responsible for:

- **Displaying notifications** based on intent and priority
- **Handling acknowledgments** for SAFETY/GOVERNANCE notifications
- **Linking to Why Layer** artifacts (DecisionSnapshot, ExecutionSnapshot)
- **Showing autonomy context** (PREVIEW/SHADOW/LIVE mode badges)
- **Managing notification lifecycle** (auto-dismiss, manual dismiss, persistence)

**Design Principle:** Notifications are **interrupts**, not inbox items. The UI should make it immediately clear why the human was interrupted and what action (if any) is required.

### 10.2 WebSocket Message Format

Notifications arrive via WebSocket with the following structure:

```typescript
interface WebSocketNotificationMessage {
  type: "notification" | "pending_notification";
  data: {
    notification_id: string;              // UUID
    notification_type: string;            // e.g., "safety.kill_switch"
    intent: "SAFETY" | "GOVERNANCE" | "OPERATIONAL" | "INFORMATIONAL";
    delivery_mode: "GUARANTEED" | "BEST_EFFORT";
    irreversible: boolean;                // True if action is irreversible
    priority: "HIGH" | "NORMAL" | "LOW";
    title: string;                        // Max 200 chars
    message: string;                       // Max 4000 chars
    metadata: Record<string, any>;        // Additional context
    source: string;                       // Producer identifier
    created_at: string;                   // ISO 8601 timestamp
    require_ack: boolean;                 // True if acknowledgment required
    ack_status: "PENDING" | "ACKED" | "DISMISSED" | "TIMED_OUT" | null;
    ack_timeout_at?: string;              // ISO 8601 timestamp (if require_ack)
    // Autonomy context (v1.2)
    autonomy_mode?: "PREVIEW" | "SHADOW" | "LIVE";
    agent_id?: string;                    // UUID
    plan_id?: string;                     // UUID (optional)
    decision_snapshot_id?: string;        // UUID (optional) - Why Layer link
    execution_snapshot_id?: string;       // UUID (optional)
    skip_snapshot_id?: string;            // UUID (optional)
    // Reconnection flag
    is_reconnect_replay?: boolean;        // True if sent on reconnect
  };
}
```

**Message Types:**
- `"notification"`: Real-time notification (new event)
- `"pending_notification"`: Replayed notification on WebSocket reconnect (see §10.7)

### 10.3 Visual Treatment by Intent

The UI must visually distinguish notifications by intent to help humans quickly understand urgency and required action.

| Intent | Color Scheme | Icon | Position | Auto-dismiss | Sound |
|--------|-------------|------|----------|--------------|-------|
| **SAFETY** | Red background (`#dc2626`), white text | 🚨 | **Modal overlay** (blocks interaction) | **Never** (requires ack) | Alert sound (optional) |
| **GOVERNANCE** | Orange background (`#ea580c`), white text | 📋 | **Top banner** (persistent) | **Never** (requires ack) | None |
| **OPERATIONAL** | Yellow background (`#ca8a04`), dark text | ⚙️ | **Toast** (bottom-right) | 10 seconds | None |
| **INFORMATIONAL** | Blue background (`#2563eb`), white text | ℹ️ | **Toast** (bottom-right) | 5 seconds | None |

**Priority Modifiers:**
- **HIGH priority**: Add pulsing animation, increase size by 20%
- **NORMAL priority**: Standard size
- **LOW priority**: Reduce opacity to 80%, smaller font

**Irreversible Indicator:**
- If `irreversible: true`, add a **bold border** (2px) and warning icon (⚠️) next to title
- For SAFETY + irreversible, consider a **confirmation step** before allowing ack/dismiss

### 10.4 Component Structure

#### 10.4.1 TypeScript Interface

```typescript
interface NotificationDisplay {
  // Core fields (from WebSocket message)
  notification_id: string;
  notification_type: string;
  intent: NotificationIntent;
  priority: Priority;
  title: string;
  message: string;
  metadata: Record<string, any>;
  source: string;
  created_at: string;

  // Acknowledgment
  require_ack: boolean;
  ack_status: AckStatus | null;
  ack_timeout_at?: string;

  // Autonomy context
  autonomy_mode?: AutonomyMode;
  agent_id?: string;
  plan_id?: string;
  decision_snapshot_id?: string;
  execution_snapshot_id?: string;
  skip_snapshot_id?: string;

  // UI state
  isDismissed: boolean;
  isExpanded: boolean;
  timeRemaining?: number;  // Seconds until auto-dismiss (if applicable)
}

type NotificationIntent = "SAFETY" | "GOVERNANCE" | "OPERATIONAL" | "INFORMATIONAL";
type Priority = "HIGH" | "NORMAL" | "LOW";
type AckStatus = "PENDING" | "ACKED" | "DISMISSED" | "TIMED_OUT";
type AutonomyMode = "PREVIEW" | "SHADOW" | "LIVE";
```

#### 10.4.2 Component Hierarchy

```
<NotificationContainer>
  ├── <NotificationModal>          // SAFETY (blocks interaction)
  ├── <NotificationBanner>         // GOVERNANCE (top of page)
  └── <NotificationToastStack>     // OPERATIONAL/INFORMATIONAL (bottom-right)
      └── <NotificationToast>      // Individual toast
          ├── <NotificationHeader>
          │   ├── <IntentIcon>
          │   ├── <Title>
          │   ├── <AutonomyBadge>   // [PREVIEW] [SHADOW] [LIVE]
          │   └── <DismissButton>   // X button (if not require_ack)
          ├── <NotificationBody>
          │   ├── <Message>
          │   ├── <Metadata>        // Expandable (if metadata present)
          │   └── <WhyLayerLink>     // If decision_snapshot_id present
          └── <NotificationActions>  // If require_ack
              ├── <AcknowledgeButton>
              └── <DismissButton>    // Only if allow_dismiss=true
```

### 10.5 Acknowledgment UI

#### 10.5.1 Requirements

**SAFETY and GOVERNANCE notifications** with `require_ack: true` **must** show acknowledgment buttons. The UI should:

1. **Block interaction** (for SAFETY) or show persistent banner (for GOVERNANCE) until ack/dismiss
2. **Show countdown timer** if `ack_timeout_at` is present
3. **Disable other actions** until acknowledgment is complete
4. **POST acknowledgment** to `/v1/notifications/{notification_id}/ack`

#### 10.5.2 Acknowledgment API

```typescript
// POST /v1/notifications/{notification_id}/ack
interface AckRequest {
  ack_status: "ACKED" | "DISMISSED";
  // Optional: User identity (from JWT)
  acked_by?: string;
}

interface AckResponse {
  notification_id: string;
  ack_status: "ACKED" | "DISMISSED";
  acked_at: string;
  response_time_seconds?: number;
}
```

**Example Implementation:**

```typescript
async function acknowledgeNotification(
  notificationId: string,
  ackStatus: "ACKED" | "DISMISSED"
): Promise<void> {
  const response = await fetch(`/v1/notifications/${notificationId}/ack`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ack_status: ackStatus }),
  });

  if (!response.ok) {
    throw new Error(`Acknowledgment failed: ${response.statusText}`);
  }

  // Update local state
  updateNotificationStatus(notificationId, ackStatus);
}
```

#### 10.5.3 Acknowledgment Button States

| State | Button Text | Action | Visual |
|-------|------------|--------|--------|
| **PENDING** | "Acknowledge" / "Dismiss" | POST to `/ack` endpoint | Enabled, primary color |
| **ACKED** | "Acknowledged ✓" | None (disabled) | Green, disabled |
| **DISMISSED** | "Dismissed" | None (disabled) | Gray, disabled |
| **TIMED_OUT** | "Timed Out" | None (disabled) | Red, disabled |

**SAFETY Intent Special Handling:**
- **"Acknowledge"** button should be **primary** (green/blue)
- **"Dismiss"** button should be **secondary** (gray) with confirmation dialog:
  - "Are you sure you want to dismiss this SAFETY notification?"
  - This prevents accidental dismissal of critical alerts

#### 10.5.4 Timeout Countdown

If `ack_timeout_at` is present, show a countdown:

```typescript
function calculateTimeRemaining(ackTimeoutAt: string): number {
  const timeout = new Date(ackTimeoutAt).getTime();
  const now = Date.now();
  return Math.max(0, Math.floor((timeout - now) / 1000)); // seconds
}

// Display: "Acknowledge within 14:32" (if time remaining > 0)
// Display: "Timed out" (if time remaining = 0)
```

**Visual Treatment:**
- **> 5 minutes remaining**: Green countdown
- **1-5 minutes remaining**: Yellow countdown
- **< 1 minute remaining**: Red countdown, pulsing animation
- **Timed out**: Red "TIMED_OUT" badge, disable buttons

### 10.6 Why Layer Integration

Notifications can link to **Why Layer** artifacts (Phase 17.2) via snapshot IDs:

- `decision_snapshot_id`: Links to DecisionSnapshot (policy/governance decisions)
- `execution_snapshot_id`: Links to ExecutionSnapshot (trade execution details)
- `skip_snapshot_id`: Links to SkipSnapshot (trade skip reasons)

#### 10.6.1 Display Pattern

If any snapshot ID is present, show a **"View Decision"** or **"View Details"** link:

```typescript
function renderWhyLayerLink(notification: NotificationDisplay): JSX.Element | null {
  const snapshotId =
    notification.decision_snapshot_id ||
    notification.execution_snapshot_id ||
    notification.skip_snapshot_id;

  if (!snapshotId) return null;

  const snapshotType = notification.decision_snapshot_id ? "decision" :
                       notification.execution_snapshot_id ? "execution" : "skip";

  return (
    <a
      href={`/atp/snapshots/${snapshotType}/${snapshotId}`}
      className="why-layer-link"
      target="_blank"
    >
      🔗 View {snapshotType === "decision" ? "Decision" :
               snapshotType === "execution" ? "Execution" : "Skip"} Details
    </a>
  );
}
```

**Visual Treatment:**
- **Icon**: 🔗 (link icon)
- **Position**: Below message, before actions
- **Style**: Underlined, intent-colored text
- **Behavior**: Opens in new tab (preserves notification context)

### 10.7 Autonomy Mode Badges

Every notification includes `autonomy_mode` (PREVIEW, SHADOW, LIVE). Display this as a **badge** next to the title:

```typescript
function renderAutonomyBadge(mode: AutonomyMode): JSX.Element {
  const badges = {
    PREVIEW: { label: "PREVIEW", color: "#6b7280", bg: "#f3f4f6" },
    SHADOW: { label: "SHADOW", color: "#d97706", bg: "#fef3c7" },
    LIVE: { label: "LIVE", color: "#dc2626", bg: "#fee2e2" },
  };

  const badge = badges[mode];
  return (
    <span
      className="autonomy-badge"
      style={{ color: badge.color, backgroundColor: badge.bg }}
    >
      [{badge.label}]
    </span>
  );
}
```

**Position:** Immediately after the intent icon, before the title.

**Purpose:** Helps humans understand the **operating context** — a SAFETY alert in PREVIEW mode is less urgent than in LIVE mode.

### 10.8 Notification Lifecycle

#### 10.8.1 Auto-dismiss (OPERATIONAL/INFORMATIONAL)

Notifications with `require_ack: false` should auto-dismiss:

| Intent | Auto-dismiss Time |
|--------|-------------------|
| OPERATIONAL | 10 seconds |
| INFORMATIONAL | 5 seconds |

**Implementation:**

```typescript
function useAutoDismiss(
  notification: NotificationDisplay,
  onDismiss: (id: string) => void
): void {
  useEffect(() => {
    if (notification.require_ack) return; // Don't auto-dismiss if ack required

    const timeout = notification.intent === "OPERATIONAL" ? 10000 : 5000;
    const timer = setTimeout(() => {
      onDismiss(notification.notification_id);
    }, timeout);

    return () => clearTimeout(timer);
  }, [notification, onDismiss]);
}
```

**Visual Feedback:**
- Show a **progress bar** indicating time remaining
- Pause auto-dismiss on **hover** (user is reading)
- Resume on **mouse leave**

#### 10.8.2 Manual Dismiss

**OPERATIONAL/INFORMATIONAL:**
- Show **X button** in top-right corner
- Dismissing removes notification immediately (no API call needed)

**SAFETY/GOVERNANCE with `require_ack: true`:**
- **"Dismiss"** button calls `/ack` endpoint with `ack_status: "DISMISSED"`
- **Confirmation dialog** for SAFETY intent (see §10.5.3)

#### 10.8.3 Persistence

**SAFETY/GOVERNANCE with `require_ack: true`:**
- **Persist in localStorage** until acknowledged
- **Replay on page reload** (query `/v1/notifications/pending` or use WebSocket reconnect handler)
- **Remove from localStorage** once acked/dismissed

**OPERATIONAL/INFORMATIONAL:**
- **No persistence** — these are ephemeral
- **Lost on page reload** (by design)

### 10.9 WebSocket Reconnection Handling

When a user reconnects via WebSocket, the backend sends **pending notifications** (see §5.4). The UI should:

1. **Receive** `type: "pending_notification"` messages
2. **Display** them with `is_reconnect_replay: true` flag
3. **Show a banner**: "Reconnected. Showing X pending notifications."
4. **Highlight** replayed notifications differently (e.g., gray border)

**Example:**

```typescript
function handleWebSocketMessage(message: WebSocketNotificationMessage): void {
  if (message.type === "pending_notification") {
    // Mark as replayed
    const notification = {
      ...message.data,
      isReconnectReplay: true,
    };

    // Show banner if first replayed notification
    if (!hasShownReconnectBanner) {
      showBanner(`Reconnected. Showing ${count} pending notifications.`);
      hasShownReconnectBanner = true;
    }

    displayNotification(notification);
  } else if (message.type === "notification") {
    // Real-time notification
    displayNotification(message.data);
  }
}
```

### 10.10 Notification Grouping

When multiple notifications arrive rapidly, consider **grouping** by intent:

**Grouping Rules:**
- **SAFETY**: Never group (each requires individual attention)
- **GOVERNANCE**: Group by `notification_type` (e.g., "3 approval requests")
- **OPERATIONAL**: Group by `source` (e.g., "5 execution alerts")
- **INFORMATIONAL**: Group all (e.g., "10 system updates")

**Visual Treatment:**
- Show **grouped notification** with count badge
- **Click to expand** and see individual notifications
- **Acknowledge group** acknowledges all (for GOVERNANCE)

### 10.11 Error Handling

#### 10.11.1 Acknowledgment Failures

If acknowledgment POST fails:

1. **Show error toast**: "Failed to acknowledge notification. Retrying..."
2. **Retry** with exponential backoff (3 attempts)
3. **If all retries fail**: Show persistent error state
   - "Unable to acknowledge. Please refresh the page."
   - **Fallback**: Allow manual refresh or show notification ID for support

#### 10.11.2 WebSocket Disconnection

If WebSocket disconnects:

1. **Show banner**: "Connection lost. Reconnecting..."
2. **Poll** `/v1/notifications/pending` every 30 seconds as fallback
3. **On reconnect**: Process pending notifications (see §10.9)

### 10.12 Accessibility

**WCAG 2.1 AA Compliance:**

- **Color contrast**: Intent colors must meet 4.5:1 ratio for text
- **Keyboard navigation**: All buttons must be keyboard-accessible
- **Screen readers**: Announce intent and priority (e.g., "SAFETY notification: Kill switch activated")
- **Focus management**: SAFETY modals trap focus until ack/dismiss
- **ARIA labels**: All interactive elements must have labels

**Example ARIA:**

```html
<div
  role="alert"
  aria-live="assertive"
  aria-label={`${intent} notification: ${title}`}
>
  <h2>{title}</h2>
  <p>{message}</p>
  {require_ack && (
    <button
      aria-label="Acknowledge notification"
      onClick={() => acknowledge(notification_id, "ACKED")}
    >
      Acknowledge
    </button>
  )}
</div>
```

### 10.13 Example Implementation (React)

```typescript
import { useEffect, useState } from "react";

interface NotificationProps {
  notification: NotificationDisplay;
  onAcknowledge: (id: string, status: "ACKED" | "DISMISSED") => Promise<void>;
  onDismiss: (id: string) => void;
}

export function NotificationComponent({
  notification,
  onAcknowledge,
  onDismiss,
}: NotificationProps) {
  const [timeRemaining, setTimeRemaining] = useState<number | null>(null);

  // Calculate timeout countdown
  useEffect(() => {
    if (!notification.ack_timeout_at) return;

    const interval = setInterval(() => {
      const remaining = calculateTimeRemaining(notification.ack_timeout_at!);
      setTimeRemaining(remaining);
      if (remaining === 0) {
        clearInterval(interval);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [notification.ack_timeout_at]);

  // Auto-dismiss for non-ack notifications
  useAutoDismiss(notification, onDismiss);

  const intentStyles = getIntentStyles(notification.intent);
  const isModal = notification.intent === "SAFETY";
  const isBanner = notification.intent === "GOVERNANCE";
  const isToast = ["OPERATIONAL", "INFORMATIONAL"].includes(notification.intent);

  return (
    <div
      className={`notification notification-${notification.intent.toLowerCase()}`}
      style={intentStyles}
      role="alert"
      aria-live={isModal ? "assertive" : "polite"}
    >
      <div className="notification-header">
        <span className="intent-icon">{getIntentIcon(notification.intent)}</span>
        {notification.autonomy_mode && (
          <AutonomyBadge mode={notification.autonomy_mode} />
        )}
        <h3>{notification.title}</h3>
        {!notification.require_ack && (
          <button
            className="dismiss-button"
            onClick={() => onDismiss(notification.notification_id)}
            aria-label="Dismiss notification"
          >
            ×
          </button>
        )}
      </div>

      <div className="notification-body">
        <p>{notification.message}</p>

        {notification.decision_snapshot_id && (
          <WhyLayerLink
            snapshotId={notification.decision_snapshot_id}
            type="decision"
          />
        )}

        {notification.metadata && Object.keys(notification.metadata).length > 0 && (
          <MetadataExpander metadata={notification.metadata} />
        )}
      </div>

      {notification.require_ack && (
        <div className="notification-actions">
          {timeRemaining !== null && timeRemaining > 0 && (
            <span className="timeout-countdown">
              Acknowledge within {formatTime(timeRemaining)}
            </span>
          )}
          {notification.ack_status === "TIMED_OUT" && (
            <span className="timeout-badge">Timed Out</span>
          )}

          <button
            className="ack-button"
            onClick={() => onAcknowledge(notification.notification_id, "ACKED")}
            disabled={notification.ack_status !== "PENDING"}
          >
            {notification.ack_status === "ACKED" ? "Acknowledged ✓" : "Acknowledge"}
          </button>

          {notification.intent === "SAFETY" ? (
            <button
              className="dismiss-button-secondary"
              onClick={() => {
                if (confirm("Are you sure you want to dismiss this SAFETY notification?")) {
                  onAcknowledge(notification.notification_id, "DISMISSED");
                }
              }}
              disabled={notification.ack_status !== "PENDING"}
            >
              Dismiss
            </button>
          ) : (
            <button
              className="dismiss-button"
              onClick={() => onAcknowledge(notification.notification_id, "DISMISSED")}
              disabled={notification.ack_status !== "PENDING"}
            >
              Dismiss
            </button>
          )}
        </div>
      )}
    </div>
  );
}
```

### 10.14 Testing Checklist

Before deploying UI integration, verify:

- [ ] **SAFETY notifications** block interaction until ack/dismiss
- [ ] **GOVERNANCE notifications** show persistent banner
- [ ] **OPERATIONAL/INFORMATIONAL** auto-dismiss after correct timeout
- [ ] **Acknowledgment** POSTs to correct endpoint with correct payload
- [ ] **Why Layer links** navigate to correct snapshot URLs
- [ ] **Autonomy badges** display correctly for all modes
- [ ] **Reconnection** replays pending notifications
- [ ] **Keyboard navigation** works for all interactive elements
- [ ] **Screen reader** announces intent and priority
- [ ] **Color contrast** meets WCAG 2.1 AA standards
- [ ] **Error handling** shows retry UI for failed acknowledgments
- [ ] **Grouping** works correctly for rapid notifications

---

## 11. Rollout Plan

### Week 1-2: Foundation
- [ ] Create `src/notification/` directory structure
- [ ] Implement models, SDK, service
- [ ] Implement Slack and Email adapters
- [ ] ~~Set up RQ queues and workers~~ *(Production uses async FastAPI delivery -- see Implementation Note in 1.1.1)*
- [ ] Unit tests for SDK and service

### Week 3-4: Reliability
- [ ] Implement deduplication
- [ ] Implement rate limiting
- [ ] Add audit logging
- [ ] Create database migration
- [ ] Integration tests

### Week 5-6: Integration
- [ ] Migrate ExecutionAlerts
- [ ] Add WebSocket adapter
- [ ] Integrate Agent Governor
- [ ] Add PagerDuty adapter
- [ ] End-to-end testing
- [ ] Documentation

---

## 12. Reference Implementation Skeleton

### 12.1 Overview

This section provides a **reference implementation skeleton** for the UNS ports & adapters layer. This is intentionally **interfaces + adapters only** (no orchestration logic, no retries, no queues, no persistence). It's designed to drop into ATP as the "ports & adapters" foundation, with the full UNS service layer built on top.

**Design Philosophy:**
- **Ports & Adapters Pattern**: Clean separation between domain interfaces and channel implementations
- **Transport-agnostic**: Domain models don't depend on delivery mechanisms
- **Testable**: Adapters can be easily mocked/stubbed for testing
- **Extensible**: New channels can be added by implementing `NotificationChannelAdapter`

**What's Included:**
- Domain models (`NotificationEvent`, `AutonomyContext`, etc.)
- Adapter interfaces (`NotificationChannelAdapter`, `NotificationRouter`, etc.)
- Channel adapter skeletons (Slack, Email, PagerDuty, WebSocket, Null)
- Adapter registry for dependency injection

**What's NOT Included** (these belong in the UNS service layer):
- Routing rules / policy registry lookups
- Deduplication + summary pulse logic
- Rate limiting
- Queueing + retries
- Persistence + audit log writes
- Webhook endpoints for ACK ingestion

### 12.2 Directory Structure

```
src/notifications/
  __init__.py
  domain.py                    # Domain models (NotificationEvent, AutonomyContext, etc.)
  interfaces.py                # Adapter interfaces and protocols
  dispatcher.py                # Simple dispatcher (optional, still adapters-only)
  registry.py                  # Adapter registry for DI
  adapters/
    __init__.py
    slack_adapter.py
    pagerduty_adapter.py
    email_adapter.py
    websocket_adapter.py
    null_adapter.py            # Safe default (no-op) adapter
```

**Note:** This structure differs slightly from the full UNS implementation (§2) which includes service logic, deduplication, rate limiting, etc. This skeleton is the **foundation layer** that the full UNS service will use.

### 12.3 Domain Models (`src/notifications/domain.py`)

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class NotificationIntent(str, Enum):
    INFORMATIONAL = "INFORMATIONAL"
    OPERATIONAL = "OPERATIONAL"
    GOVERNANCE = "GOVERNANCE"
    SAFETY = "SAFETY"


class NotificationCategory(str, Enum):
    EXECUTION = "EXECUTION"
    GOVERNANCE = "GOVERNANCE"
    POLICY = "POLICY"
    RISK = "RISK"
    SYSTEM = "SYSTEM"


class AutonomyMode(str, Enum):
    PREVIEW = "PREVIEW"
    SHADOW = "SHADOW"
    LIVE = "LIVE"


class DeliveryMode(str, Enum):
    BEST_EFFORT = "BEST_EFFORT"
    GUARANTEED = "GUARANTEED"


class Channel(str, Enum):
    WEBSOCKET = "WEBSOCKET"
    SLACK = "SLACK"
    EMAIL = "EMAIL"
    PAGERDUTY = "PAGERDUTY"


class AckStatus(str, Enum):
    ACKED = "ACKED"
    DISMISSED = "DISMISSED"
    TIMED_OUT = "TIMED_OUT"


class AutonomyContext(BaseModel):
    autonomy_mode: AutonomyMode
    agent_id: Optional[str] = None
    plan_id: Optional[str] = None
    decision_snapshot_id: Optional[str] = None
    execution_snapshot_id: Optional[str] = None


class NotificationEvent(BaseModel):
    """
    Canonical event UNS accepts.
    This is intentionally transport-agnostic.
    """
    event_id: str = Field(..., description="UUID (string). Assigned by producer or UNS.")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Semantics
    intent: NotificationIntent
    category: NotificationCategory
    notification_type: str = Field(..., description="Stable taxonomy key (e.g., safety.kill_switch_activated)")
    reversible: bool = True
    delivery_mode: DeliveryMode = DeliveryMode.BEST_EFFORT
    require_ack: bool = False

    # Human-facing content
    title: str
    summary: str
    details: Dict[str, Any] = Field(default_factory=dict)

    # Context
    autonomy: AutonomyContext
    trace_id: Optional[str] = None

    # Cognitive safety
    dedup_key: Optional[str] = None


class ChannelDeliveryResult(BaseModel):
    channel: Channel
    success: bool
    provider_message_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    delivered_at: Optional[datetime] = None


class NotificationDispatchResult(BaseModel):
    event_id: str
    attempted_channels: List[ChannelDeliveryResult] = Field(default_factory=list)


class AckEvent(BaseModel):
    """
    Acknowledgment is a signal (telemetry + governance), not a workflow.
    """
    event_id: str
    status: AckStatus
    acked_at: datetime = Field(default_factory=datetime.utcnow)
    acked_by: Optional[str] = None  # internal user id (preferred)
    acked_by_external: Optional[str] = None  # slack user id, pagerduty user id, etc.
    channel: Optional[Channel] = None
    note: Optional[str] = None
```

**Key Differences from Full UNS Models (§3.1):**
- `NotificationEvent` uses `summary` instead of `message` (more semantic)
- `NotificationCategory` added for additional classification
- `AckEvent` includes `acked_by_external` for external system user IDs
- Simplified structure focused on transport-agnostic domain concepts

### 12.4 Adapter Interfaces (`src/notifications/interfaces.py`)

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Optional, Protocol, Sequence

from .domain import (
    AckEvent,
    Channel,
    ChannelDeliveryResult,
    NotificationDispatchResult,
    NotificationEvent,
)


class NotificationChannelAdapter(ABC):
    """
    Adapter for delivering notifications to a single channel.
    No retries, no policy logic, no queue logic here.
    """

    @abstractmethod
    def channel(self) -> Channel:
        raise NotImplementedError

    @abstractmethod
    def deliver(self, event: NotificationEvent) -> ChannelDeliveryResult:
        """
        Deliver a single event to this channel.
        Must return a structured result; must not raise for normal delivery failures.
        """
        raise NotImplementedError


class AckIngestAdapter(ABC):
    """
    Optional adapter for ingesting acknowledgments from external systems (Slack buttons,
    PagerDuty webhooks, etc.). This is just the port; actual webhook plumbing lives elsewhere.
    """

    @abstractmethod
    def ingest(self, ack: AckEvent) -> None:
        raise NotImplementedError


class NotificationRouter(Protocol):
    """
    Pure interface: decides which channels should be attempted for a given event.
    Implementation may consult policy registry/config, but router is not an adapter.
    """

    def route(self, event: NotificationEvent) -> Sequence[Channel]: ...


class NotificationDispatcher(Protocol):
    """
    Minimal port: dispatch to a set of channel adapters.
    A higher-level UNS service can wrap this with dedup/rate-limit/queue.
    """

    def dispatch(self, event: NotificationEvent, channels: Iterable[Channel]) -> NotificationDispatchResult: ...


class AdapterRegistry(Protocol):
    """
    Lookup for channel adapters.
    """

    def get(self, channel: Channel) -> Optional[NotificationChannelAdapter]: ...
    def all_channels(self) -> Sequence[Channel]: ...
```

### 12.5 Channel Adapters

#### 12.5.1 Null Adapter (`src/notifications/adapters/null_adapter.py`)

```python
from __future__ import annotations

from datetime import datetime

from ..domain import Channel, ChannelDeliveryResult, NotificationEvent
from ..interfaces import NotificationChannelAdapter


class NullAdapter(NotificationChannelAdapter):
    """
    Safe default adapter: does nothing, always succeeds.
    Useful for local dev or disabling a channel without code changes.
    """

    def __init__(self, channel: Channel):
        self._channel = channel

    def channel(self) -> Channel:
        return self._channel

    def deliver(self, event: NotificationEvent) -> ChannelDeliveryResult:
        return ChannelDeliveryResult(
            channel=self._channel,
            success=True,
            provider_message_id=None,
            delivered_at=datetime.utcnow(),
        )
```

#### 12.5.2 Slack Adapter (`src/notifications/adapters/slack_adapter.py`)

```python
from __future__ import annotations

from datetime import datetime
from typing import Optional

from ..domain import Channel, ChannelDeliveryResult, NotificationEvent
from ..interfaces import NotificationChannelAdapter


class SlackAdapter(NotificationChannelAdapter):
    """
    Interface-only skeleton. Plug in your Slack client later.
    """

    def __init__(self, webhook_url: str, default_channel: Optional[str] = None):
        self.webhook_url = webhook_url
        self.default_channel = default_channel

    def channel(self) -> Channel:
        return Channel.SLACK

    def deliver(self, event: NotificationEvent) -> ChannelDeliveryResult:
        # TODO: Implement Slack POST (webhook or chat.postMessage via SDK)
        # NOTE: Do NOT throw for expected failures; return structured error.
        return ChannelDeliveryResult(
            channel=Channel.SLACK,
            success=False,
            error_code="NOT_IMPLEMENTED",
            error_message="SlackAdapter.deliver is a skeleton (not implemented).",
            delivered_at=None,
        )
```

#### 12.5.3 PagerDuty Adapter (`src/notifications/adapters/pagerduty_adapter.py`)

```python
from __future__ import annotations

from ..domain import Channel, ChannelDeliveryResult, NotificationEvent
from ..interfaces import NotificationChannelAdapter


class PagerDutyAdapter(NotificationChannelAdapter):
    """
    Interface-only skeleton for triggering incidents/events.
    """

    def __init__(self, integration_key: str):
        self.integration_key = integration_key

    def channel(self) -> Channel:
        return Channel.PAGERDUTY

    def deliver(self, event: NotificationEvent) -> ChannelDeliveryResult:
        return ChannelDeliveryResult(
            channel=Channel.PAGERDUTY,
            success=False,
            error_code="NOT_IMPLEMENTED",
            error_message="PagerDutyAdapter.deliver is a skeleton (not implemented).",
        )
```

#### 12.5.4 Email Adapter (`src/notifications/adapters/email_adapter.py`)

```python
from __future__ import annotations

from typing import Optional

from ..domain import Channel, ChannelDeliveryResult, NotificationEvent
from ..interfaces import NotificationChannelAdapter


class EmailAdapter(NotificationChannelAdapter):
    """
    Interface-only skeleton (SES/SendGrid/Mailgun/etc).
    """

    def __init__(self, from_address: str, default_to: Optional[str] = None):
        self.from_address = from_address
        self.default_to = default_to

    def channel(self) -> Channel:
        return Channel.EMAIL

    def deliver(self, event: NotificationEvent) -> ChannelDeliveryResult:
        return ChannelDeliveryResult(
            channel=Channel.EMAIL,
            success=False,
            error_code="NOT_IMPLEMENTED",
            error_message="EmailAdapter.deliver is a skeleton (not implemented).",
        )
```

#### 12.5.5 WebSocket Adapter (`src/notifications/adapters/websocket_adapter.py`)

```python
from __future__ import annotations

from ..domain import Channel, ChannelDeliveryResult, NotificationEvent
from ..interfaces import NotificationChannelAdapter


class WebSocketAdapter(NotificationChannelAdapter):
    """
    Interface-only skeleton. This adapter should publish to your existing WS broadcast layer.
    Keep it ephemeral; persistence belongs to audit/timeline systems.
    """

    def __init__(self, topic_prefix: str = "notifications"):
        self.topic_prefix = topic_prefix

    def channel(self) -> Channel:
        return Channel.WEBSOCKET

    def deliver(self, event: NotificationEvent) -> ChannelDeliveryResult:
        return ChannelDeliveryResult(
            channel=Channel.WEBSOCKET,
            success=False,
            error_code="NOT_IMPLEMENTED",
            error_message="WebSocketAdapter.deliver is a skeleton (not implemented).",
        )
```

**Design Principle:** All adapters return structured `ChannelDeliveryResult` objects rather than raising exceptions for normal delivery failures. This allows the service layer to handle failures gracefully and implement retry/fallback logic.

### 12.6 Adapter Registry (`src/notifications/registry.py`)

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Sequence

from .domain import Channel
from .interfaces import AdapterRegistry, NotificationChannelAdapter


@dataclass(frozen=True)
class InMemoryAdapterRegistry(AdapterRegistry):
    """
    Simple registry for DI wiring.
    Real systems may build this from config.
    """
    adapters: Dict[Channel, NotificationChannelAdapter]

    def get(self, channel: Channel) -> Optional[NotificationChannelAdapter]:
        return self.adapters.get(channel)

    def all_channels(self) -> Sequence[Channel]:
        return list(self.adapters.keys())
```

### 12.7 Simple Dispatcher (`src/notifications/dispatcher.py`)

```python
from __future__ import annotations

from typing import Iterable

from .domain import Channel, NotificationDispatchResult, NotificationEvent
from .interfaces import AdapterRegistry, NotificationDispatcher


class SimpleDispatcher(NotificationDispatcher):
    """
    Dispatches to adapters. No dedup, no rate limits, no retries.
    This is still interface-level plumbing—no policy logic.
    """

    def __init__(self, registry: AdapterRegistry):
        self.registry = registry

    def dispatch(self, event: NotificationEvent, channels: Iterable[Channel]) -> NotificationDispatchResult:
        result = NotificationDispatchResult(event_id=event.event_id)

        for ch in channels:
            adapter = self.registry.get(ch)
            if not adapter:
                result.attempted_channels.append(
                    ChannelDeliveryResult(
                        channel=ch,
                        success=False,
                        error_code="ADAPTER_MISSING",
                        error_message=f"No adapter registered for channel={ch}",
                    )
                )
                continue

            delivery = adapter.deliver(event)
            result.attempted_channels.append(delivery)

        return result
```

### 12.8 Usage Example

```python
from uuid import uuid4
import os
from src.notifications import (
    NotificationEvent,
    NotificationIntent,
    NotificationCategory,
    AutonomyMode,
    AutonomyContext,
    DeliveryMode,
    Channel,
    InMemoryAdapterRegistry,
    SimpleDispatcher,
)
from src.notifications.adapters import (
    SlackAdapter,
    EmailAdapter,
    WebSocketAdapter,
    NullAdapter,
)

# Build adapter registry
registry = InMemoryAdapterRegistry({
    Channel.SLACK: SlackAdapter(webhook_url=os.getenv("SLACK_WEBHOOK_URL")),
    Channel.EMAIL: EmailAdapter(from_address="alerts@example.com"),
    Channel.WEBSOCKET: WebSocketAdapter(),
    # Use NullAdapter for channels not yet implemented
    Channel.PAGERDUTY: NullAdapter(Channel.PAGERDUTY),
})

# Create dispatcher
dispatcher = SimpleDispatcher(registry)

# Create notification event
event = NotificationEvent(
    event_id=str(uuid4()),
    intent=NotificationIntent.SAFETY,
    category=NotificationCategory.RISK,
    notification_type="safety.kill_switch_activated",
    reversible=False,
    delivery_mode=DeliveryMode.GUARANTEED,
    require_ack=True,
    title="Kill Switch Activated",
    summary="Trading halted by operator",
    autonomy=AutonomyContext(
        autonomy_mode=AutonomyMode.LIVE,
        agent_id="agent-123",
    ),
)

# Dispatch (higher-level service will add routing, dedup, rate limiting)
result = dispatcher.dispatch(event, [Channel.SLACK, Channel.WEBSOCKET])
```

### 12.9 Router Interface + YAML-driven Routing Config

#### 12.9.1 YAML Policy File (`config/notification_routing.yaml`)

The router uses a YAML configuration file as the source of truth for routing rules:

```yaml
version: 1
updated_at: "2026-01-19"
description: "UNS routing rules for Agentic Trading Intelligence Platform"

defaults:
  # Fallbacks when rule doesn't specify fields
  delivery_mode: BEST_EFFORT
  require_ack: false
  channels: [WEBSOCKET]
  dedup:
    window_seconds: 60
    strategy: KEY_ONLY   # KEY_ONLY | KEY_AND_INTENT | OFF

autonomy_overrides:
  # Mode-specific modifiers (applied after base rule match)
  PREVIEW:
    suppress_channels: [PAGERDUTY, EMAIL]
    force_delivery_mode: BEST_EFFORT
  SHADOW:
    suppress_channels: [PAGERDUTY]
    force_delivery_mode: BEST_EFFORT
  LIVE:
    # no suppression by default
    {}

rules:
  # --- SAFETY (irreversible) ---
  - id: safety.kill_switch_activated
    match:
      notification_type: "safety.kill_switch_activated"
    intent: SAFETY
    category: SYSTEM
    reversible: false
    delivery_mode: GUARANTEED
    require_ack: true
    channels: [WEBSOCKET, SLACK, PAGERDUTY]
    dedup:
      window_seconds: 5
      strategy: KEY_AND_INTENT

  - id: safety.circuit_breaker_engaged
    match:
      notification_type: "safety.circuit_breaker_engaged"
    intent: SAFETY
    category: RISK
    reversible: false
    delivery_mode: GUARANTEED
    require_ack: true
    channels: [WEBSOCKET, SLACK, PAGERDUTY]

  # --- GOVERNANCE (approval required) ---
  - id: governance.policy_delta_pending_approval
    match:
      notification_type: "governance.policy_delta_pending_approval"
    intent: GOVERNANCE
    category: POLICY
    reversible: false
    delivery_mode: GUARANTEED
    require_ack: true
    channels: [WEBSOCKET, SLACK, EMAIL]
    dedup:
      window_seconds: 300
      strategy: KEY_AND_INTENT

  # --- OPERATIONAL ---
  - id: operational.market_data_lag
    match:
      notification_type: "operational.market_data_lag"
    intent: OPERATIONAL
    category: SYSTEM
    reversible: true
    delivery_mode: BEST_EFFORT
    require_ack: false
    channels: [WEBSOCKET, SLACK]
    dedup:
      window_seconds: 120
      strategy: KEY_ONLY

  # --- INFORMATIONAL ---
  - id: informational.trade_skipped_summary_pulse
    match:
      notification_type: "informational.trade_skipped_summary_pulse"
    intent: INFORMATIONAL
    category: EXECUTION
    reversible: true
    delivery_mode: BEST_EFFORT
    require_ack: false
    channels: [WEBSOCKET]
    dedup:
      window_seconds: 60
      strategy: KEY_ONLY

fallback:
  # If no rules match, apply defaults + autonomy_overrides
  use_defaults: true
```

#### 12.9.2 Router Implementation (`src/notifications/routing.py`)

```python
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Protocol, Sequence, Tuple

from pydantic import BaseModel, Field

from .domain import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    NotificationCategory,
    NotificationEvent,
    NotificationIntent,
)


class DedupStrategy(str, Enum):
    OFF = "OFF"
    KEY_ONLY = "KEY_ONLY"
    KEY_AND_INTENT = "KEY_AND_INTENT"


class DedupConfig(BaseModel):
    window_seconds: int = Field(60, ge=0)
    strategy: DedupStrategy = DedupStrategy.KEY_ONLY


class RoutingDefaults(BaseModel):
    delivery_mode: DeliveryMode = DeliveryMode.BEST_EFFORT
    require_ack: bool = False
    channels: List[Channel] = Field(default_factory=lambda: [Channel.WEBSOCKET])
    dedup: DedupConfig = Field(default_factory=DedupConfig)


class RuleMatch(BaseModel):
    notification_type: str


class RoutingRule(BaseModel):
    id: str
    match: RuleMatch

    # These fields define the semantic envelope for the event.
    intent: NotificationIntent
    category: NotificationCategory
    reversible: bool

    # Delivery + UX constraints
    delivery_mode: DeliveryMode = DeliveryMode.BEST_EFFORT
    require_ack: bool = False
    channels: List[Channel] = Field(default_factory=list)
    dedup: Optional[DedupConfig] = None


class AutonomyOverride(BaseModel):
    suppress_channels: List[Channel] = Field(default_factory=list)
    force_delivery_mode: Optional[DeliveryMode] = None


class RoutingPolicy(BaseModel):
    version: int = 1
    updated_at: Optional[str] = None
    description: Optional[str] = None

    defaults: RoutingDefaults = Field(default_factory=RoutingDefaults)
    autonomy_overrides: Dict[AutonomyMode, AutonomyOverride] = Field(default_factory=dict)
    rules: List[RoutingRule] = Field(default_factory=list)

    # Fallback behavior
    fallback_use_defaults: bool = True


class RoutedNotification(BaseModel):
    """
    Output of routing. Higher layers decide dispatch strategy (queue/retry/etc).
    """
    channels: List[Channel]
    delivery_mode: DeliveryMode
    require_ack: bool
    dedup: DedupConfig

    # Derived info helpful for downstream layers
    matched_rule_id: Optional[str] = None
    dedup_key_effective: Optional[str] = None


class NotificationRouter(Protocol):
    """
    Pure routing: no IO, no persistence.
    Deterministic mapping: event + policy -> RoutedNotification
    """
    def route(self, event: NotificationEvent) -> RoutedNotification: ...


class YamlPolicyRouter(NotificationRouter):
    """
    Deterministic router driven by RoutingPolicy.
    """
    def __init__(self, policy: RoutingPolicy):
        self.policy = policy

    def route(self, event: NotificationEvent) -> RoutedNotification:
        rule = self._match_rule(event.notification_type)

        # Start with defaults
        delivery_mode = self.policy.defaults.delivery_mode
        require_ack = self.policy.defaults.require_ack
        channels = list(self.policy.defaults.channels)
        dedup = self.policy.defaults.dedup

        matched_rule_id = None

        # Overlay rule if match
        if rule:
            matched_rule_id = rule.id
            delivery_mode = rule.delivery_mode
            require_ack = rule.require_ack
            channels = list(rule.channels) if rule.channels else channels
            dedup = rule.dedup or dedup

        # Autonomy override
        mode = event.autonomy.autonomy_mode
        override = self.policy.autonomy_overrides.get(mode)
        if override:
            if override.force_delivery_mode:
                delivery_mode = override.force_delivery_mode
            if override.suppress_channels:
                channels = [c for c in channels if c not in override.suppress_channels]

        # Dedup effective key
        dedup_key_effective = self._compute_dedup_key(event, dedup)

        return RoutedNotification(
            channels=channels,
            delivery_mode=delivery_mode,
            require_ack=require_ack,
            dedup=dedup,
            matched_rule_id=matched_rule_id,
            dedup_key_effective=dedup_key_effective,
        )

    def _match_rule(self, notification_type: str) -> Optional[RoutingRule]:
        for r in self.policy.rules:
            if r.match.notification_type == notification_type:
                return r
        return None

    def _compute_dedup_key(self, event: NotificationEvent, dedup: DedupConfig) -> Optional[str]:
        if dedup.strategy == DedupStrategy.OFF:
            return None

        base = event.dedup_key or event.notification_type
        if dedup.strategy == DedupStrategy.KEY_ONLY:
            return base
        if dedup.strategy == DedupStrategy.KEY_AND_INTENT:
            return f"{base}:{event.intent.value}"
        return base
```

**Design Principles:**
- **Deterministic**: Same event + policy always produces same routing result
- **IO-free**: No database lookups, no external calls
- **Mode-aware**: Autonomy overrides applied after rule matching
- **Fallback-safe**: Defaults ensure routing always succeeds

**Note:** This router is intentionally deterministic and IO-free. Higher layers (UNS core) decide how to apply dedup windows, retries, queueing, etc.

### 12.10 OpenAPI Contract

#### 12.10.1 API Endpoints

The reference implementation defines two core endpoints:

- **`POST /v1/notifications/send`**: Send a notification event to UNS
- **`POST /v1/notifications/ack`**: Record an acknowledgment for a notification event

#### 12.10.2 OpenAPI 3.0 Specification

```yaml
openapi: 3.0.3
info:
  title: ATP Unified Notification Service API
  version: "1.0"

paths:
  /v1/notifications/send:
    post:
      summary: Send a notification event to UNS
      description: >
        Accepts a canonical NotificationEvent (transport-agnostic).
        UNS routes to channels according to routing policy and returns a dispatch receipt.
        This endpoint MUST NOT block trading execution; use BEST_EFFORT by default unless event declares GUARANTEED.
      operationId: sendNotification
      tags: [Notifications]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/NotificationEvent"
      responses:
        "200":
          description: Dispatch receipt
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/NotificationDispatchReceipt"
        "400":
          description: Invalid event payload (schema validation)
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"
        "422":
          description: Semantic validation failed (e.g., missing autonomy context for SAFETY/GOVERNANCE)
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"

  /v1/notifications/ack:
    post:
      summary: Record an acknowledgment for a notification event
      description: >
        Records an acknowledgment signal (ACKED, DISMISSED, TIMED_OUT).
        Acks are telemetry + governance signals and may be used to unlock state transitions (control-plane),
        but MUST NOT gate in-flight executions.
      operationId: acknowledgeNotification
      tags: [Notifications]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/AckEvent"
      responses:
        "200":
          description: Ack accepted
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/AckReceipt"
        "400":
          description: Invalid ack payload (schema validation)
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"
        "404":
          description: Event not found (optional enforcement)
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"

components:
  schemas:
    NotificationIntent:
      type: string
      enum: [INFORMATIONAL, OPERATIONAL, GOVERNANCE, SAFETY]

    NotificationCategory:
      type: string
      enum: [EXECUTION, GOVERNANCE, POLICY, RISK, SYSTEM]

    AutonomyMode:
      type: string
      enum: [PREVIEW, SHADOW, LIVE]

    DeliveryMode:
      type: string
      enum: [BEST_EFFORT, GUARANTEED]

    Channel:
      type: string
      enum: [WEBSOCKET, SLACK, EMAIL, PAGERDUTY]

    AckStatus:
      type: string
      enum: [ACKED, DISMISSED, TIMED_OUT]

    AutonomyContext:
      type: object
      required: [autonomy_mode]
      properties:
        autonomy_mode:
          $ref: "#/components/schemas/AutonomyMode"
        agent_id:
          type: string
          nullable: true
        plan_id:
          type: string
          nullable: true
        decision_snapshot_id:
          type: string
          nullable: true
        execution_snapshot_id:
          type: string
          nullable: true

    NotificationEvent:
      type: object
      required:
        - event_id
        - intent
        - category
        - notification_type
        - title
        - summary
        - autonomy
      properties:
        event_id:
          type: string
          description: UUID string
        timestamp:
          type: string
          format: date-time
        intent:
          $ref: "#/components/schemas/NotificationIntent"
        category:
          $ref: "#/components/schemas/NotificationCategory"
        notification_type:
          type: string
          description: Stable taxonomy key (e.g., safety.kill_switch_activated)
        reversible:
          type: boolean
          default: true
        delivery_mode:
          $ref: "#/components/schemas/DeliveryMode"
        require_ack:
          type: boolean
          default: false
        title:
          type: string
        summary:
          type: string
        details:
          type: object
          additionalProperties: true
        autonomy:
          $ref: "#/components/schemas/AutonomyContext"
        trace_id:
          type: string
          nullable: true
        dedup_key:
          type: string
          nullable: true

    ChannelDeliveryResult:
      type: object
      required: [channel, success]
      properties:
        channel:
          $ref: "#/components/schemas/Channel"
        success:
          type: boolean
        provider_message_id:
          type: string
          nullable: true
        error_code:
          type: string
          nullable: true
        error_message:
          type: string
          nullable: true
        delivered_at:
          type: string
          format: date-time
          nullable: true

    NotificationDispatchReceipt:
      type: object
      required: [event_id, routed_channels, delivery_mode, require_ack, dispatch_results]
      properties:
        event_id:
          type: string
        routed_channels:
          type: array
          items:
            $ref: "#/components/schemas/Channel"
        delivery_mode:
          $ref: "#/components/schemas/DeliveryMode"
        require_ack:
          type: boolean
        matched_rule_id:
          type: string
          nullable: true
        dedup_key_effective:
          type: string
          nullable: true
        dispatch_results:
          type: array
          items:
            $ref: "#/components/schemas/ChannelDeliveryResult"

    AckEvent:
      type: object
      required: [event_id, status]
      properties:
        event_id:
          type: string
        status:
          $ref: "#/components/schemas/AckStatus"
        acked_at:
          type: string
          format: date-time
        acked_by:
          type: string
          nullable: true
          description: Internal user id (preferred)
        acked_by_external:
          type: string
          nullable: true
          description: Slack/PagerDuty user identity
        channel:
          $ref: "#/components/schemas/Channel"
        note:
          type: string
          nullable: true

    AckReceipt:
      type: object
      required: [event_id, status, accepted]
      properties:
        event_id:
          type: string
        status:
          $ref: "#/components/schemas/AckStatus"
        accepted:
          type: boolean
        message:
          type: string
          nullable: true

    ErrorResponse:
      type: object
      required: [error]
      properties:
        error:
          type: string
        message:
          type: string
          nullable: true
        details:
          type: object
          nullable: true
          additionalProperties: true
```

#### 12.10.3 API Contract Notes

**`POST /v1/notifications/send`:**
- Returns a **dispatch receipt** that includes routing outcome (`matched_rule_id`, `dedup_key_effective`) + per-channel delivery results
- **MUST NOT block trading execution** — use BEST_EFFORT by default unless event declares GUARANTEED
- **422 Unprocessable Entity** returned for semantic validation failures:
  - SAFETY/GOVERNANCE missing `autonomy.autonomy_mode`
  - `require_ack: true` but ack metadata is malformed (depending on strictness)

**`POST /v1/notifications/ack`:**
- **Ack is a signal**, not a workflow
- May be used to unlock state transitions (control-plane) but **MUST NOT gate in-flight executions**
- **404 Not Found** is optional enforcement (some implementations may accept acks for unknown events for idempotency)

### 12.11 Integration with Full UNS Service

This skeleton provides the **foundation layer** for the full UNS implementation:

1. **Domain models** can be extended with additional fields as needed
2. **Adapters** implement the `NotificationChannelAdapter` interface, which the full UNS service (§3.4) will use
3. **Registry** provides dependency injection for adapters
4. **Router** provides deterministic routing based on YAML policy (can be extended with database-backed policies in full UNS)
5. **Dispatcher** can be wrapped by the full UNS service to add:
   - Deduplication (§4.1)
   - Rate limiting (§4.2)
   - Retry logic (§3.3)
   - Audit logging (§4.3)
6. **API endpoints** provide the HTTP contract for producers and acknowledgment handlers

**Migration Path:**
- Start with this skeleton for rapid prototyping
- Implement adapter `deliver()` methods as needed
- Build full UNS service layer on top using these interfaces
- Gradually migrate from skeleton models to full UNS models (§3.1) as features are added
- Extend router with database-backed policy registry (§4.6) for dynamic policy updates

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-19 | Claude | Initial specification |
| 1.1 | 2026-01-19 | Claude | Intent/delivery-mode framework: Added NotificationIntent enum (SAFETY, GOVERNANCE, OPERATIONAL, INFORMATIONAL), DeliveryMode enum (GUARANTEED, BEST_EFFORT), irreversible field, safety-path strictness, cognitive safety framing, DLQ escalation handler |
| 1.2 | 2026-01-19 | Claude | Autonomy awareness and acknowledgment framework: Added AutonomyMode enum (PREVIEW, SHADOW, LIVE), AutonomyContext model (autonomy_mode, agent_id, plan_id, decision_snapshot_id), AckStatus enum (PENDING, ACKED, DISMISSED, TIMED_OUT), mode-dependent routing in SDK, acknowledgment module with timeout handling, NotificationPolicy model for declarative YAML-based policies, PolicyRegistry, updated migration with autonomy/ack fields, notification_policies table |
| 1.2.1 | 2026-01-19 | Claude | Pre-lock polish: Control plane boundary statement (§1.1), producer contract validation in SDK (§3.2), acked_by identity source of truth (§4.5), block_autonomy_until_ack semantics (§4.6), DLQ visibility invariant (§3.3) — aligning with func spec v1.2 gaps 2.1–2.4 |
| 1.2.2 | 2026-01-19 | Claude | Team feedback fixes: (1) Architecture trade-off doc for RQ vs Redis Streams (§1.1.1), (2) RQ failure handler wiring + UNSWorker class (§7.3), (3) GUARANTEED sequential fallback delivery (§3.3), (4) Policy hot-reload with 60s cache TTL (§4.6), (5) WebSocket adapter thread-safe async bridge (§3.4), (6) Dedup summary pulse loop prevention (§4.1), (7) Policy lookup in SDK send() (§3.2), (8) WebSocket reconnection handler for pending notifications (§5.4), (9) Scheduler requirement documentation (§7.4) |
| 1.2.3 | 2026-01-19 | Claude | GUARANTEED delivery test documentation: Full pytest test suite for sequential fallback chain (§8.3), test coverage requirements matrix with 9 mandatory scenarios (§8.4), integration test checklist for staging environment (§8.5) |
| 1.2.4 | 2026-01-19 | Claude | UI Integration Guide: Added comprehensive frontend integration documentation (§10) covering WebSocket message format, visual treatment by intent, component structure, acknowledgment UI patterns, Why Layer integration, autonomy mode badges, notification lifecycle, reconnection handling, grouping, error handling, accessibility (WCAG 2.1 AA), and React example implementation |
| 1.2.5 | 2026-01-19 | Claude | Clarity improvements: (1) Added explicit GUARANTEED delivery semantics statement (§1.1), (2) Sharpened block_autonomy_until_ack language with explicit forbidden operations (§4.6), (3) Added anti-pattern warning callout for execution blocking (§1.1), (4) Added idempotency guarantee statement in deduplication (§4.1), (5) Added human trust calibration note in ack event emission (§4.5), (6) Added Notification Type Taxonomy appendix (§13) with namespace rules and naming conventions |
| 1.2.6 | 2026-01-19 | Claude | Reference Implementation Skeleton: Added ports & adapters reference implementation (§12) with domain models, adapter interfaces, channel adapter skeletons (Slack, Email, PagerDuty, WebSocket, Null), adapter registry, and simple dispatcher. This provides a foundation layer for rapid prototyping before building the full UNS service |
| 1.2.7 | 2026-01-19 | Claude | Reference Implementation Extensions: Added router interface with YAML-driven routing config (§12.9) including RoutingPolicy models, YamlPolicyRouter implementation, and example YAML configuration. Added OpenAPI 3.0 contract (§12.10) for `/v1/notifications/send` and `/v1/notifications/ack` endpoints with complete schema definitions |
| 2.0 | 2026-01-19 | Claude | Version bump for standalone UNS service: This version marks the transition to a standalone, reusable notification service architecture. All previous features remain intact. |
| 2.1 | 2026-02-10 | Claude | Policy engine stabilization: §4.6 implementation note added — actual implementation uses dataclass (not Pydantic), full lifecycle (DRAFT→PREVIEW→ACTIVE→RETIRED), DB persistence (`NotificationPolicyModel` + migration 053), version chain (`previous_version_id`), hot-reload (`POST /policies/reload`), YAML loader (`policy_loader.py`), MIP-225 compliance (producer hooks no longer pass channels/delivery_mode), 6 default policies, updated DB schema to match actual `atp.notification_policy` DDL |
| 2.0.1 | 2026-02-10 | Claude | Architecture mismatch corrections: Added Implementation Notes to sections §1.1.1, §1.2, §3.2, §3.3, and §7 clarifying that the production implementation uses direct async FastAPI delivery orchestration (not RQ or Redis Streams). Redis is used for deduplication and rate limiting only. Design-phase content retained for historical context. Updated §11 rollout plan to reflect actual architecture. |
