# Unified Notification Service (UNS)

Control-plane notification and acknowledgment service.

## Features

- Multi-channel delivery (Slack, Email, WebSocket, PagerDuty)
- Intent-based routing (SAFETY, GOVERNANCE, OPERATIONAL, INFORMATIONAL)
- Guaranteed and best-effort delivery modes
- Rate limiting and deduplication
- Acknowledgment tracking

## Installation

```bash
pip install -e ".[all]"
```

## Usage

```python
from notification.adapters import get_adapter, SlackConfig
from notification.models import Channel

config = SlackConfig(
    bot_token="xoxb-...",
    default_channel="#alerts",
)
adapter = get_adapter(Channel.SLACK, config=config)
```
