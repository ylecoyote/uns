"""Shared SQLAlchemy declarative base and enum types.

The single ``Base`` declared here keeps the SQLAlchemy metadata registry
unified across audit, policy, learning, and websocket-replay submodules so
migrations and ORM relationships continue to work after the split.

This module is package-private (leading underscore). External callers should
import shared symbols via ``db.models`` re-exports.
"""

from __future__ import annotations

from enum import Enum

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class DeliveryStatusDB(str, Enum):
    """Database enum for delivery status."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    DEDUPLICATED = "DEDUPLICATED"
    RATE_LIMITED = "RATE_LIMITED"


class AckStatusDB(str, Enum):
    """Database enum for acknowledgment status."""

    PENDING = "PENDING"
    ACKED = "ACKED"
    DISMISSED = "DISMISSED"
    TIMED_OUT = "TIMED_OUT"
