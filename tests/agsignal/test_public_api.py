"""Guard the agsignal top-level public API against accidental drift.

Phase 3 Task 7 added the four service-layer write functions to the
``from agsignal import …`` surface (``send_signal``, ``simulate_signal``,
``acknowledge``, ``dismiss``) — they parallel the ``SignalClient`` SDK
affordance. Read functions stay scoped to ``agsignal.queries.X`` by design;
exporting them at the top level would clutter the SDK surface without
parallel SDK affordance.

These tests lock both decisions into the public-API contract.
"""

from __future__ import annotations

import agsignal


def test_public_api_includes_service_layer_write_functions() -> None:
    """Top-level ``from agsignal import …`` resolves the four write functions."""
    assert hasattr(agsignal, "send_signal")
    assert hasattr(agsignal, "simulate_signal")
    assert hasattr(agsignal, "acknowledge")
    assert hasattr(agsignal, "dismiss")
    # Each must also appear in __all__ so wildcard import + IDE completion both work.
    for name in ("send_signal", "simulate_signal", "acknowledge", "dismiss"):
        assert name in agsignal.__all__, f"{name!r} missing from agsignal.__all__"


def test_public_api_excludes_service_layer_read_functions() -> None:
    """Read functions stay scoped to ``agsignal.queries`` by design.

    Exporting them at the top level would clutter the SDK surface without
    parallel SDK affordance. Consumers reach for them as
    ``from agsignal.queries import …`` to signal the operational nature.
    """
    read_functions = (
        "get_ack_status",
        "get_notification_status",
        "get_effective_policy",
        "list_invariants",
        "get_invariants_summary",
        "list_deliveries",
        "list_audit_events",
        "get_delivery_timeline",
    )
    for name in read_functions:
        assert not hasattr(agsignal, name), (
            f"{name!r} unexpectedly exported from agsignal top level — "
            "read functions are scoped to agsignal.queries by design"
        )
        assert name not in agsignal.__all__


def test_queries_submodule_exposes_read_functions() -> None:
    """The read functions ARE reachable via ``agsignal.queries``."""
    from agsignal import queries

    expected = (
        "get_ack_status",
        "get_notification_status",
        "get_effective_policy",
        "list_invariants",
        "get_invariants_summary",
        "list_deliveries",
        "list_audit_events",
        "get_delivery_timeline",
    )
    for name in expected:
        assert hasattr(queries, name), f"agsignal.queries.{name} missing"


def test_all_entries_are_resolvable() -> None:
    """Every name in ``__all__`` resolves to an attribute on the module.

    Catches drift between ``__all__`` and the actual import block.
    """
    for name in agsignal.__all__:
        assert hasattr(agsignal, name), (
            f"agsignal.__all__ lists {name!r} but it is not defined on the module"
        )
