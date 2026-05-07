"""Tests for AGSignal Console package structure.

These tests verify that the UI package is properly structured
and that all expected modules can be imported.
"""

from __future__ import annotations

from pathlib import Path

import pytest


class TestPackageStructure:
    """Tests for package structure and imports."""

    def test_ui_package_imports(self) -> None:
        """Test that the main UI package can be imported."""
        import apps.ui

        assert hasattr(apps.ui, "__version__")
        assert apps.ui.__version__ == "0.1.0"

    def test_src_package_imports(self) -> None:
        """Test that the src subpackage can be imported."""
        from apps.ui import src

        assert src is not None

    def test_api_package_imports(self) -> None:
        """Test that the api subpackage can be imported."""
        from apps.ui.src import api

        assert api is not None

    def test_pages_package_imports(self) -> None:
        """Test that the pages subpackage can be imported."""
        from apps.ui.src import pages

        assert pages is not None

    def test_components_package_imports(self) -> None:
        """Test that the components subpackage can be imported."""
        from apps.ui.src import components

        assert components is not None

    def test_layouts_package_imports(self) -> None:
        """Test that the layouts subpackage can be imported."""
        from apps.ui.src import layouts

        assert layouts is not None

    def test_hooks_package_imports(self) -> None:
        """Test that the hooks subpackage can be imported."""
        from apps.ui.src import hooks

        assert hooks is not None

    def test_utils_package_imports(self) -> None:
        """Test that the utils subpackage can be imported."""
        from apps.ui.src import utils

        assert utils is not None


class TestConfigModule:
    """Tests for the configuration module."""

    def test_config_imports(self) -> None:
        """Test that the config module can be imported."""
        from apps.ui.src import config

        assert hasattr(config, "UIConfig")
        assert hasattr(config, "get_config")
        assert hasattr(config, "reset_config")

    def test_ui_config_defaults(self) -> None:
        """Test UIConfig default values."""
        from apps.ui.src.config import UIConfig

        cfg = UIConfig()
        assert cfg.api_base_url == "http://localhost:8000"
        assert cfg.debug is False
        assert cfg.request_timeout == 30
        assert cfg.api_version == "v1"

    def test_ui_config_api_prefix(self) -> None:
        """Test UIConfig api_prefix property."""
        from apps.ui.src.config import UIConfig

        cfg = UIConfig(api_base_url="http://example.com", api_version="v2")
        assert cfg.api_prefix == "http://example.com/api/v2"

    def test_ui_config_frozen(self) -> None:
        """Test that UIConfig is immutable."""
        from dataclasses import FrozenInstanceError

        from apps.ui.src.config import UIConfig

        cfg = UIConfig()
        with pytest.raises(FrozenInstanceError):
            cfg.api_base_url = "http://other.com"  # type: ignore[misc]

    def test_get_config_caching(self) -> None:
        """Test that get_config returns cached instance."""
        from apps.ui.src.config import get_config, reset_config

        reset_config()
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    def test_reset_config_clears_cache(self) -> None:
        """Test that reset_config clears the cache."""
        import os

        from apps.ui.src.config import get_config, reset_config

        # Get initial config
        reset_config()
        config1 = get_config()

        # Change environment and reset
        original = os.environ.get("UNS_UI_DEBUG")
        try:
            os.environ["UNS_UI_DEBUG"] = "true"
            reset_config()
            config2 = get_config()
            assert config1 is not config2
            assert config2.debug is True
        finally:
            # Restore original
            if original is None:
                os.environ.pop("UNS_UI_DEBUG", None)
            else:
                os.environ["UNS_UI_DEBUG"] = original
            reset_config()


class TestAuthModule:
    """Tests for the authentication module."""

    def test_auth_imports(self) -> None:
        """Test that the auth module can be imported."""
        from apps.ui.src import auth

        assert hasattr(auth, "AuthStatus")
        assert hasattr(auth, "UserContext")
        assert hasattr(auth, "AuthProvider")
        assert hasattr(auth, "NoOpAuthProvider")
        assert hasattr(auth, "get_auth_provider")
        assert hasattr(auth, "get_current_user")

    def test_auth_status_enum(self) -> None:
        """Test AuthStatus enum values."""
        from apps.ui.src.auth import AuthStatus

        assert AuthStatus.AUTHENTICATED == "authenticated"
        assert AuthStatus.ANONYMOUS == "anonymous"
        assert AuthStatus.EXPIRED == "expired"

    def test_user_context_anonymous(self) -> None:
        """Test UserContext for anonymous user."""
        from apps.ui.src.auth import AuthStatus, UserContext

        user = UserContext(
            user_id="anonymous",
            status=AuthStatus.ANONYMOUS,
        )
        assert user.is_authenticated is False

    def test_user_context_authenticated(self) -> None:
        """Test UserContext for authenticated user."""
        from apps.ui.src.auth import AuthStatus, UserContext

        user = UserContext(
            user_id="user-123",
            status=AuthStatus.AUTHENTICATED,
            display_name="Test User",
        )
        assert user.is_authenticated is True

    def test_noop_auth_provider(self) -> None:
        """Test NoOpAuthProvider returns anonymous user."""
        from apps.ui.src.auth import AuthStatus, NoOpAuthProvider

        provider = NoOpAuthProvider()
        user = provider.get_current_user()
        assert user.status == AuthStatus.ANONYMOUS
        assert provider.is_authenticated() is False

    def test_get_auth_provider_default(self) -> None:
        """Test get_auth_provider returns NoOpAuthProvider by default."""
        from apps.ui.src.auth import NoOpAuthProvider, get_auth_provider, reset_auth_provider

        reset_auth_provider()
        provider = get_auth_provider()
        assert isinstance(provider, NoOpAuthProvider)

    def test_get_current_user_convenience(self) -> None:
        """Test get_current_user convenience function."""
        from apps.ui.src.auth import get_current_user, reset_auth_provider

        reset_auth_provider()
        user = get_current_user()
        assert user.user_id == "anonymous"


class TestRouterModule:
    """Tests for the router module."""

    def test_router_imports(self) -> None:
        """Test that the router module can be imported."""
        from apps.ui.src import router

        assert hasattr(router, "Route")
        assert hasattr(router, "HTTPMethod")
        assert hasattr(router, "ALL_ROUTES")
        assert hasattr(router, "get_all_routes")

    def test_http_method_get_only(self) -> None:
        """Test that only GET method is supported (read-only)."""
        from apps.ui.src.router import HTTPMethod

        # v1 is read-only, only GET is supported
        assert HTTPMethod.GET == "GET"

    def test_all_routes_exist(self) -> None:
        """Test that all expected routes are defined."""
        from apps.ui.src.router import get_all_routes

        routes = get_all_routes()
        route_names = {r.name for r in routes}

        assert "deliveries_list" in route_names
        assert "deliveries_detail" in route_names
        assert "policy_inspector" in route_names
        assert "invariants_list" in route_names
        assert "invariants_summary" in route_names
        assert "audit_list" in route_names

    def test_all_routes_are_get(self) -> None:
        """Test that all routes use GET method (read-only posture)."""
        from apps.ui.src.router import HTTPMethod, get_all_routes

        routes = get_all_routes()
        for route in routes:
            assert route.method == HTTPMethod.GET, f"Route {route.name} should be GET only"

    def test_get_route_by_name(self) -> None:
        """Test get_route_by_name lookup."""
        from apps.ui.src.router import get_route_by_name

        route = get_route_by_name("deliveries_list")
        assert route is not None
        assert route.path == "/deliveries"

        missing = get_route_by_name("nonexistent")
        assert missing is None

    def test_build_path_with_params(self) -> None:
        """Test build_path parameter substitution."""
        from apps.ui.src.router import ROUTE_DELIVERIES_DETAIL, build_path

        path = build_path(ROUTE_DELIVERIES_DETAIL, notification_id="abc-123")
        assert path == "/deliveries/abc-123"


class TestMainLayout:
    """Tests for the main layout module."""

    def test_layout_imports(self) -> None:
        """Test that the main layout module can be imported."""
        from apps.ui.src.layouts import main_layout

        assert hasattr(main_layout, "NavigationRoute")
        assert hasattr(main_layout, "NavigationItem")
        assert hasattr(main_layout, "NAVIGATION_ITEMS")

    def test_navigation_routes_exist(self) -> None:
        """Test that all expected navigation routes are defined."""
        from apps.ui.src.layouts.main_layout import NavigationRoute

        assert NavigationRoute.DELIVERIES == "/deliveries"
        assert NavigationRoute.POLICY == "/policy"
        assert NavigationRoute.INVARIANTS == "/invariants"
        assert NavigationRoute.AUDIT == "/audit"

    def test_navigation_items(self) -> None:
        """Test that navigation items are properly configured."""
        from apps.ui.src.layouts.main_layout import get_navigation_items

        items = get_navigation_items()
        assert len(items) == 4

        labels = {item.label for item in items}
        assert "Deliveries" in labels
        assert "Policy" in labels
        assert "Invariants" in labels
        assert "Audit" in labels

    def test_get_route_for_label(self) -> None:
        """Test get_route_for_label lookup."""
        from apps.ui.src.layouts.main_layout import NavigationRoute, get_route_for_label

        assert get_route_for_label("Deliveries") == NavigationRoute.DELIVERIES
        assert get_route_for_label("deliveries") == NavigationRoute.DELIVERIES
        assert get_route_for_label("nonexistent") is None


class TestPageModules:
    """Tests for page modules."""

    def test_deliveries_page_imports(self) -> None:
        """Test that the deliveries page module can be imported."""
        from apps.ui.src.pages import deliveries

        assert hasattr(deliveries, "DeliveriesPageState")
        assert hasattr(deliveries, "DeliveryDetailPageState")
        assert hasattr(deliveries, "get_deliveries_page_title")
        assert hasattr(deliveries, "get_available_filters")

    def test_deliveries_filters(self) -> None:
        """Test that deliveries page has expected filters."""
        from apps.ui.src.pages.deliveries import get_available_filters

        filters = get_available_filters()
        assert "intent" in filters
        assert "delivery_mode" in filters
        assert "status" in filters
        assert "agent_id" in filters
        assert "autonomy_mode" in filters
        assert "channel" in filters

    def test_policy_page_imports(self) -> None:
        """Test that the policy page module can be imported."""
        from apps.ui.src.pages import policy

        assert hasattr(policy, "PolicyInspectorPageState")
        assert hasattr(policy, "get_policy_page_title")
        assert hasattr(policy, "get_intent_options")
        assert hasattr(policy, "get_autonomy_mode_options")

    def test_policy_options(self) -> None:
        """Test that policy page has expected options."""
        from apps.ui.src.pages.policy import get_autonomy_mode_options, get_intent_options

        intents = get_intent_options()
        assert "SAFETY" in intents
        assert "GOVERNANCE" in intents
        assert "OPERATIONAL" in intents
        assert "INFORMATIONAL" in intents

        modes = get_autonomy_mode_options()
        assert "PREVIEW" in modes
        assert "SHADOW" in modes
        assert "LIVE" in modes

    def test_invariants_page_imports(self) -> None:
        """Test that the invariants page module can be imported."""
        from apps.ui.src.pages import invariants

        assert hasattr(invariants, "InvariantsPageState")
        assert hasattr(invariants, "InvariantsSummaryPageState")
        assert hasattr(invariants, "get_invariants_page_title")

    def test_invariants_filters(self) -> None:
        """Test that invariants page has expected filters."""
        from apps.ui.src.pages.invariants import get_available_filters, get_severity_options

        filters = get_available_filters()
        assert "severity" in filters
        assert "enforcement_type" in filters
        assert "status" in filters
        assert "search" in filters

        severities = get_severity_options()
        assert "HIGH" in severities
        assert "MEDIUM" in severities
        assert "LOW" in severities

    def test_audit_page_imports(self) -> None:
        """Test that the audit page module can be imported."""
        from apps.ui.src.pages import audit

        assert hasattr(audit, "AuditPageState")
        assert hasattr(audit, "get_audit_page_title")
        assert hasattr(audit, "get_event_type_options")

    def test_audit_event_types(self) -> None:
        """Test that audit page has expected event types."""
        from apps.ui.src.pages.audit import get_event_type_options

        event_types = get_event_type_options()
        assert "notification.created" in event_types
        assert "delivery.started" in event_types
        assert "delivery.succeeded" in event_types
        assert "delivery.failed" in event_types
        assert "ack.received" in event_types
        assert "escalation.triggered" in event_types


class TestReadOnlyPosture:
    """Tests to verify read-only posture is enforced."""

    def test_all_routes_are_get_only(self) -> None:
        """Verify that no POST/PUT/DELETE routes exist."""
        from apps.ui.src.router import HTTPMethod, get_all_routes

        for route in get_all_routes():
            assert route.method == HTTPMethod.GET, (
                f"Route {route.name} uses {route.method}, but UI should be read-only (GET only)"
            )

    def test_http_method_enum_only_has_get(self) -> None:
        """Verify HTTPMethod enum only defines GET for v1."""
        from apps.ui.src.router import HTTPMethod

        # Count defined methods
        methods = list(HTTPMethod)
        assert len(methods) == 1
        assert methods[0] == HTTPMethod.GET


class TestFileStructure:
    """Tests for file structure existence."""

    @pytest.fixture
    def ui_root(self) -> Path:
        """Get the UI package root path."""
        import apps.ui

        return Path(apps.ui.__file__).parent

    def test_readme_exists(self, ui_root: Path) -> None:
        """Test that README.md exists."""
        readme = ui_root / "README.md"
        assert readme.exists(), "apps/ui/README.md should exist"

    def test_readme_contains_required_sections(self, ui_root: Path) -> None:
        """Test that README has required sections."""
        readme = ui_root / "README.md"
        content = readme.read_text()

        assert "# AGSignal Console" in content
        assert "Non-Authoritative" in content
        assert "read-only" in content.lower()
        assert "Local Development" in content
        assert "UNS_API_BASE_URL" in content

    def test_init_files_exist(self, ui_root: Path) -> None:
        """Test that all __init__.py files exist."""
        expected_inits = [
            ui_root / "__init__.py",
            ui_root / "src" / "__init__.py",
            ui_root / "src" / "api" / "__init__.py",
            ui_root / "src" / "pages" / "__init__.py",
            ui_root / "src" / "components" / "__init__.py",
            ui_root / "src" / "layouts" / "__init__.py",
            ui_root / "src" / "hooks" / "__init__.py",
            ui_root / "src" / "utils" / "__init__.py",
            ui_root / "tests" / "__init__.py",
        ]
        for init_file in expected_inits:
            assert init_file.exists(), f"{init_file} should exist"
