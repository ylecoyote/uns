"""Tests for typed domain errors in :mod:`uns.errors`."""

from __future__ import annotations

from uns.errors import NotFoundError, UNSError


def test_not_found_error_carries_resource_and_identifier() -> None:
    err = NotFoundError(resource="delivery_timeline", identifier="abc-123")
    assert err.resource == "delivery_timeline"
    assert err.identifier == "abc-123"
    # Lock the message format - log lines and downstream handlers depend on it.
    assert str(err) == "delivery_timeline not found: abc-123"


def test_not_found_error_is_uns_error() -> None:
    err = NotFoundError(resource="x", identifier="y")
    assert isinstance(err, UNSError)
    assert isinstance(err, Exception)
