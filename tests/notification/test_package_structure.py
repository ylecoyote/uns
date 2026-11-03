"""
Tests for notification package structure.

Task 0 Acceptance Criteria:
- Package imports resolve
- Empty modules compile
"""

import importlib
import sys


class TestPackageStructure:
    """Test that the notification package structure is correct."""

    def test_notification_package_imports(self):
        """Test that the main notification package can be imported."""
        import src.notification

        assert src.notification is not None
        assert hasattr(src.notification, "__version__")
        assert src.notification.__version__ == "0.3.0"

    def test_notification_adapters_package_imports(self):
        """Test that the adapters subpackage can be imported."""
        import src.notification.adapters

        assert src.notification.adapters is not None

    def test_notification_integrations_package_imports(self):
        """Test that the integrations subpackage can be imported."""
        import src.notification.integrations

        assert src.notification.integrations is not None

    def test_src_package_imports(self):
        """Test that the src package can be imported."""
        import src

        assert src is not None

    def test_all_modules_compile(self):
        """Test that all notification modules compile without errors."""
        modules = [
            "src",
            "src.notification",
            "src.notification.adapters",
            "src.notification.integrations",
        ]

        for module_name in modules:
            # Remove from cache if present to force fresh import
            if module_name in sys.modules:
                del sys.modules[module_name]

            # This will raise if the module fails to compile
            module = importlib.import_module(module_name)
            assert module is not None, f"Module {module_name} failed to import"

    def test_package_docstrings_present(self):
        """Test that packages have docstrings."""
        import src.notification
        import src.notification.adapters
        import src.notification.integrations

        assert src.notification.__doc__ is not None
        assert "UNS Core compatibility package" in src.notification.__doc__

        assert src.notification.adapters.__doc__ is not None
        assert "Adapters" in src.notification.adapters.__doc__

        assert src.notification.integrations.__doc__ is not None
        assert "Integrations" in src.notification.integrations.__doc__
