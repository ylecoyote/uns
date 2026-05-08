"""Tests for typed domain errors in :mod:`agsignal.errors`."""

from __future__ import annotations

from agsignal.errors import AGSignalError, NotFoundError


def test_not_found_error_carries_resource_and_identifier() -> None:
    err = NotFoundError(resource="delivery_timeline", identifier="abc-123")
    assert err.resource == "delivery_timeline"
    assert err.identifier == "abc-123"
    assert "delivery_timeline" in str(err)
    assert "abc-123" in str(err)


def test_not_found_error_is_agsignal_error() -> None:
    err = NotFoundError(resource="x", identifier="y")
    assert isinstance(err, AGSignalError)
    assert isinstance(err, Exception)
