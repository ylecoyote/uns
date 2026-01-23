# UI Read Models

This document describes the read model adapters that connect the UI dashboard endpoints to the underlying persistence and audit stores.

## Overview

The UI dashboard requires read-only access to:
- **Delivery timelines** - History of notification deliveries and channel attempts
- **Audit events** - Detailed audit trail of delivery and acknowledgment events
- **Policy resolution** - Real-time policy resolution (already functional via PolicyRegistry)
- **System invariants** - Loaded from YAML files (already functional)

The read model adapters provide an abstraction layer between the HTTP endpoints and the data stores, enabling:
- Multiple backend implementations (in-memory, database)
- Easy testing with mock data
- Clean separation of concerns

## Quick Start

**For local demo (no database required):**
```bash
# In-memory storage, data lost on restart
uvicorn mcp_server.app:app --reload
```

**For production (with database persistence):**
```bash
export DATABASE_URL="postgresql://user:pass@localhost/uns"
uvicorn mcp_server.app:app
```

The application automatically configures the appropriate storage backend at startup based on the `DATABASE_URL` environment variable. See [Configuration](#configuration) for details.

## Architecture

```
┌──────────────────┐     ┌─────────────────────┐     ┌─────────────────┐
│   UI Endpoints   │────>│  ReadModelAdapter   │────>│   AuditStore    │
│  (routes_ui.py)  │     │    (read_models.py) │     │   (audit.py)    │
└──────────────────┘     └─────────────────────┘     └─────────────────┘
                                   │
                                   │ (implements)
                         ┌─────────┴─────────┐
                         │                   │
              ┌──────────▼──────┐   ┌────────▼────────┐
              │ InMemoryAdapter │   │ SQLAlchemyAdapter│
              │  (local demo)   │   │   (production)   │
              └─────────────────┘   └──────────────────┘
```

## Adapter Implementations

### InMemoryReadModelAdapter

**Location:** `src/mcp_server/read_models.py`

In-memory adapter suitable for local development and demos.

**Limitations (IMPORTANT):**
- Data is **lost on process restart**
- No persistence across sessions
- Limited query performance (full scan filtering)
- **Not suitable for production use**

**When to use:**
- Local development
- Demo environments
- Testing without database setup
- Quick prototyping

**Example:**
```python
from mcp_server.read_models import (
    InMemoryReadModelAdapter,
    configure_read_model_adapter,
)
from notification.audit import InMemoryAuditStore

# Create shared audit store (for both reads and writes)
audit_store = InMemoryAuditStore()

# Configure read adapter
adapter = InMemoryReadModelAdapter(audit_store=audit_store)
configure_read_model_adapter(adapter)
```

### SQLAlchemyReadModelAdapter

**Location:** `src/mcp_server/read_models.py`

Database-backed adapter for production deployments.

**Features:**
- Persistent storage
- Efficient indexed queries
- Supports pagination at database level
- Scalable for large datasets

**When to use:**
- Production deployments
- Staging environments
- Any scenario requiring data persistence

**Example:**
```python
from mcp_server.read_models import (
    create_sqlalchemy_adapter,
    configure_read_model_adapter,
)

# Create adapter with database URL
adapter = create_sqlalchemy_adapter(
    database_url="postgresql://user:pass@localhost/uns",
    create_tables=True,  # Create tables if they don't exist
)
configure_read_model_adapter(adapter)
```

## Data Models

### DeliveryFilter

Filter criteria for delivery timeline queries:

| Field | Type | Description |
|-------|------|-------------|
| `start_time` | `datetime` | Filter by created_at >= |
| `end_time` | `datetime` | Filter by created_at < |
| `status` | `DeliveryStatus` | DELIVERED, FAILED, DEDUPLICATED, RATE_LIMITED |
| `intent` | `NotificationIntent` | SAFETY, GOVERNANCE, OPERATIONAL, INFORMATIONAL |
| `delivery_mode` | `DeliveryMode` | GUARANTEED, BEST_EFFORT |
| `agent_id` | `UUID` | Filter by agent UUID |
| `autonomy_mode` | `AutonomyMode` | PREVIEW, SHADOW, LIVE |
| `notification_type` | `str` | Namespaced notification type |
| `channel` | `Channel` | SLACK, EMAIL, WEBSOCKET, PAGERDUTY |

### AuditEventFilter

Filter criteria for audit event queries:

| Field | Type | Description |
|-------|------|-------------|
| `start_time` | `datetime` | Filter by event_time >= |
| `end_time` | `datetime` | Filter by event_time < |
| `event_type` | `str` | Event type (e.g., delivery.succeeded, ack.received) |
| `notification_id` | `UUID` | Filter by notification UUID |
| `agent_id` | `UUID` | Filter by agent UUID |
| `autonomy_mode` | `AutonomyMode` | PREVIEW, SHADOW, LIVE |
| `correlation_id` | `str` | Filter by correlation ID |

### Event Types

**Delivery Events:**
- `delivery.started` - Delivery attempt initiated
- `delivery.succeeded` - Delivery completed successfully
- `delivery.failed` - Delivery failed
- `delivery.deduplicated` - Notification deduplicated
- `delivery.rate_limited` - Notification rate limited

**Acknowledgment Events:**
- `ack.pending` - Ack requirement set
- `ack.received` - User acknowledged notification
- `ack.dismissed` - User dismissed notification
- `ack.timed_out` - Ack timeout expired

## Configuration

### Automatic Startup Configuration

The application automatically configures persistence at startup via `configure_persistence()` in `app.py`. Configuration is controlled by environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | SQLAlchemy database URL | Not set (uses in-memory) |
| `UNS_CREATE_TABLES` | Create tables on startup | `true` |

**Local Demo Mode (no DATABASE_URL):**
```bash
# Uses shared in-memory storage
# Data is NOT persisted across restarts
uvicorn mcp_server.app:app --reload
```

**Production Mode (DATABASE_URL set):**
```bash
# Uses SQLAlchemy with PostgreSQL
export DATABASE_URL="postgresql://user:pass@localhost/uns"
export UNS_CREATE_TABLES="true"
uvicorn mcp_server.app:app
```

### Manual Configuration

For custom setups or testing, you can configure adapters manually:

```python
# Create app without automatic persistence config
from mcp_server.app import create_app
app = create_app(skip_persistence_config=True)

# Then configure manually
from mcp_server.read_models import (
    create_sqlalchemy_adapter,
    configure_read_model_adapter,
)
adapter = create_sqlalchemy_adapter(database_url, create_tables=True)
configure_read_model_adapter(adapter)
```

### Integration with AuditStore

The startup configuration automatically wires the audit store and read model adapter to share data:

**In-Memory Mode (local demo):**
- Creates a shared `InMemoryAuditStore`
- Configures `PersistentAuditLogger` with the shared store (writes)
- Configures `InMemoryReadModelAdapter` with the shared store (reads)
- Notifications written by the service are immediately visible in UI endpoints

**Database Mode (production):**
- Both audit logger and read adapter connect to the same database
- Uses `SQLAlchemyAuditStore` for writes
- Uses `SQLAlchemyReadModelAdapter` for reads
- Data persists across restarts

### Manual Integration (for testing)

For unit tests, you can manually share the audit store:

```python
from notification.audit import (
    InMemoryAuditStore,
    configure_audit_logger,
)
from mcp_server.read_models import (
    InMemoryReadModelAdapter,
    configure_read_model_adapter,
)

# Create shared store
audit_store = InMemoryAuditStore()

# Configure audit logger (writes)
configure_audit_logger(store=audit_store)

# Configure read adapter (reads)
adapter = InMemoryReadModelAdapter(audit_store=audit_store)
configure_read_model_adapter(adapter)
```

## Pagination

All list endpoints support cursor-based pagination:

- **Cursor:** Opaque base64-encoded string
- **Limit:** 1-100 items per page (default 25)
- **Total count:** Included when efficient to compute

Example response:
```json
{
  "items": [...],
  "pagination": {
    "next_cursor": "eyJvZmZzZXQiOiAyNX0=",
    "has_more": true,
    "total_count": 150
  }
}
```

## Testing

For testing, use the in-memory adapter with test data:

```python
import pytest
from datetime import datetime, UTC
from uuid import uuid4

from notification.audit import (
    AuditRecord,
    InMemoryAuditStore,
)
from notification.models import (
    Channel,
    DeliveryStatus,
    NotificationIntent,
    DeliveryMode,
    AutonomyMode,
)
from mcp_server.read_models import (
    InMemoryReadModelAdapter,
    DeliveryFilter,
)

@pytest.fixture
def adapter_with_data():
    store = InMemoryAuditStore()

    # Add test data
    record = AuditRecord(
        audit_id=uuid4(),
        notification_id=uuid4(),
        notification_type="test.notification",
        status=DeliveryStatus.DELIVERED,
        channels_attempted=(Channel.SLACK,),
        channels_succeeded=(Channel.SLACK,),
        channels_failed=(),
        error_message=None,
        intent="OPERATIONAL",
        delivery_mode="BEST_EFFORT",
        autonomy_mode="LIVE",
        agent_id=uuid4(),
        plan_id=None,
        decision_snapshot_id=None,
        execution_snapshot_id=None,
        skip_snapshot_id=None,
        title="Test Notification",
        source="test-source",
        correlation_id=None,
        metadata={},
        audit_metadata={},
        notification_created_at=datetime.now(UTC),
        delivered_at=datetime.now(UTC),
        audit_created_at=datetime.now(UTC),
    )
    store.save_delivery_audit(record)

    return InMemoryReadModelAdapter(audit_store=store)

def test_list_deliveries(adapter_with_data):
    result = adapter_with_data.get_deliveries(
        DeliveryFilter(),
        cursor=None,
        limit=10,
    )
    assert result.total_count == 1
    assert len(result.items) == 1
```

## Migration Path

To migrate from in-memory to database-backed storage:

1. **Set up database:**
   ```bash
   # Create PostgreSQL database
   createdb uns
   ```

2. **Configure adapter:**
   ```python
   adapter = create_sqlalchemy_adapter(
       "postgresql://user:pass@localhost/uns",
       create_tables=True,
   )
   configure_read_model_adapter(adapter)
   ```

3. **Migrate existing data (if needed):**
   ```python
   # Export from in-memory
   from notification.audit import get_audit_logger
   old_store = get_audit_logger().store

   # Import to new store
   from db.audit_store import create_sqlalchemy_audit_store
   new_store = create_sqlalchemy_audit_store(database_url)

   for record in old_store.delivery_audits:
       new_store.save_delivery_audit(record)
   ```

## Known Limitations

### In-Memory Adapter
- No data persistence
- O(n) filtering (full scan)
- Not suitable for large datasets
- Single process only

### SQLAlchemy Adapter
- Requires database setup
- JSON contains queries may vary by database dialect
- Ack records don't store full autonomy context

### General
- Attempt-level timing not captured (uses delivery timestamp)
- Generated attempt IDs (not stored in audit records)
- Ack audit events have limited context fields
