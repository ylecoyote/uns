"""Guard the uns top-level public API against accidental drift.

Phase 3 Task 7 added the four service-layer write functions to the
``from uns import …`` surface (``send_signal``, ``simulate_signal``,
``acknowledge``, ``dismiss``) - they parallel the ``SignalClient`` SDK
affordance. Read functions stay scoped to ``uns.queries.X`` by design;
exporting them at the top level would clutter the SDK surface without
parallel SDK affordance.

These tests lock both decisions into the public-API contract.
"""

from __future__ import annotations

import uns


def test_public_api_includes_service_layer_write_functions() -> None:
    """Top-level ``from uns import …`` resolves the four write functions."""
    assert hasattr(uns, "send_signal")
    assert hasattr(uns, "simulate_signal")
    assert hasattr(uns, "acknowledge")
    assert hasattr(uns, "dismiss")
    # Each must also appear in __all__ so wildcard import + IDE completion both work.
    for name in ("send_signal", "simulate_signal", "acknowledge", "dismiss"):
        assert name in uns.__all__, f"{name!r} missing from uns.__all__"


def test_public_api_excludes_service_layer_read_functions() -> None:
    """Read functions stay scoped to ``uns.queries`` by design.

    Exporting them at the top level would clutter the SDK surface without
    parallel SDK affordance. Consumers reach for them as
    ``from uns.queries import …`` to signal the operational nature.
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
        assert not hasattr(uns, name), (
            f"{name!r} unexpectedly exported from uns top level - "
            "read functions are scoped to uns.queries by design"
        )
        assert name not in uns.__all__


def test_queries_submodule_exposes_read_functions() -> None:
    """The read functions ARE reachable via ``uns.queries``."""
    from uns import queries

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
        assert hasattr(queries, name), f"uns.queries.{name} missing"


def test_all_entries_are_resolvable() -> None:
    """Every name in ``__all__`` resolves to an attribute on the module.

    Catches drift between ``__all__`` and the actual import block.
    """
    for name in uns.__all__:
        assert hasattr(uns, name), (
            f"uns.__all__ lists {name!r} but it is not defined on the module"
        )


def test_public_api_version_alignment() -> None:
    """uns and uns_mcp export matching __version__ == '0.6.1'."""
    import uns_mcp

    assert uns.__version__ == uns_mcp.__version__ == "0.6.1"
    assert "__version__" in uns.__all__
    assert "__version__" in uns_mcp.__all__
