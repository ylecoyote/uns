"""Tests for the UI boundary guardrail script.

These tests validate that the check_ui_boundary.py script correctly identifies
boundary violations in the apps/ui directory structure.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add scripts/ci to the path so we can import the module
# ruff: noqa: E402
scripts_ci_path = Path(__file__).parent.parent.parent / "scripts" / "ci"
if str(scripts_ci_path) not in sys.path:
    sys.path.insert(0, str(scripts_ci_path))

from check_ui_boundary import (
    BoundaryViolation,
    check_flask_app_patterns,
    check_python_files,
    check_templates_directory,
    is_in_legacy_reference,
)


@pytest.fixture
def mock_ui_root(tmp_path: Path) -> Path:
    """Create a mock apps/ui directory structure for testing."""
    ui_root = tmp_path / "apps" / "ui"
    ui_root.mkdir(parents=True)
    return ui_root


class TestIsInLegacyReference:
    """Tests for the is_in_legacy_reference helper function."""

    def test_file_in_legacy_reference_returns_true(self, mock_ui_root: Path) -> None:
        """Files under legacy_flask_reference should return True."""
        legacy_dir = mock_ui_root / "legacy_flask_reference"
        legacy_dir.mkdir()
        test_file = legacy_dir / "app.py"
        test_file.touch()

        assert is_in_legacy_reference(test_file, mock_ui_root) is True

    def test_nested_file_in_legacy_reference_returns_true(self, mock_ui_root: Path) -> None:
        """Deeply nested files under legacy_flask_reference should return True."""
        legacy_dir = mock_ui_root / "legacy_flask_reference" / "deep" / "nested"
        legacy_dir.mkdir(parents=True)
        test_file = legacy_dir / "module.py"
        test_file.touch()

        assert is_in_legacy_reference(test_file, mock_ui_root) is True

    def test_file_outside_legacy_reference_returns_false(self, mock_ui_root: Path) -> None:
        """Files not under legacy_flask_reference should return False."""
        test_file = mock_ui_root / "src" / "app.py"
        test_file.parent.mkdir(parents=True)
        test_file.touch()

        assert is_in_legacy_reference(test_file, mock_ui_root) is False

    def test_file_in_root_returns_false(self, mock_ui_root: Path) -> None:
        """Files directly in ui root should return False."""
        test_file = mock_ui_root / "app.py"
        test_file.touch()

        assert is_in_legacy_reference(test_file, mock_ui_root) is False


class TestCheckPythonFiles:
    """Tests for the check_python_files function."""

    def test_no_python_files_returns_empty(self, mock_ui_root: Path) -> None:
        """UI directory with no Python files should pass."""
        (mock_ui_root / "src").mkdir()
        (mock_ui_root / "src" / "App.tsx").touch()

        violations = check_python_files(mock_ui_root)

        assert violations == []

    def test_python_file_in_root_is_violation(self, mock_ui_root: Path) -> None:
        """Python file in ui root is a violation."""
        (mock_ui_root / "app.py").touch()

        violations = check_python_files(mock_ui_root)

        assert len(violations) == 1
        assert violations[0].rule == "NO_PYTHON_IN_CANONICAL_UI"

    def test_python_file_in_src_is_violation(self, mock_ui_root: Path) -> None:
        """Python file in ui/src is a violation."""
        src = mock_ui_root / "src"
        src.mkdir()
        (src / "helpers.py").touch()

        violations = check_python_files(mock_ui_root)

        assert len(violations) == 1
        assert violations[0].rule == "NO_PYTHON_IN_CANONICAL_UI"

    def test_python_file_in_legacy_reference_is_allowed(self, mock_ui_root: Path) -> None:
        """Python files in legacy_flask_reference are allowed."""
        legacy = mock_ui_root / "legacy_flask_reference"
        legacy.mkdir()
        (legacy / "app.py").touch()
        (legacy / "routes.py").touch()

        violations = check_python_files(mock_ui_root)

        assert violations == []

    def test_multiple_python_files_all_reported(self, mock_ui_root: Path) -> None:
        """All Python files outside legacy reference are reported."""
        (mock_ui_root / "app.py").touch()
        (mock_ui_root / "__init__.py").touch()
        pages = mock_ui_root / "pages"
        pages.mkdir()
        (pages / "routes.py").touch()

        violations = check_python_files(mock_ui_root)

        assert len(violations) == 3

    def test_nonexistent_ui_root_returns_empty(self, tmp_path: Path) -> None:
        """Non-existent UI directory should return empty list."""
        nonexistent = tmp_path / "does_not_exist"

        violations = check_python_files(nonexistent)

        assert violations == []


class TestCheckTemplatesDirectory:
    """Tests for the check_templates_directory function."""

    def test_no_templates_directory_returns_empty(self, mock_ui_root: Path) -> None:
        """UI directory without templates folder should pass."""
        (mock_ui_root / "src").mkdir()
        (mock_ui_root / "components").mkdir()

        violations = check_templates_directory(mock_ui_root)

        assert violations == []

    def test_templates_directory_is_violation(self, mock_ui_root: Path) -> None:
        """Templates directory in UI root is a violation."""
        (mock_ui_root / "templates").mkdir()

        violations = check_templates_directory(mock_ui_root)

        assert len(violations) == 1
        assert violations[0].rule == "NO_TEMPLATES_DIRECTORY"

    def test_nested_templates_directory_is_violation(self, mock_ui_root: Path) -> None:
        """Nested templates directory is also a violation."""
        pages = mock_ui_root / "pages" / "templates"
        pages.mkdir(parents=True)

        violations = check_templates_directory(mock_ui_root)

        assert len(violations) == 1
        assert violations[0].rule == "NO_TEMPLATES_DIRECTORY"

    def test_templates_in_legacy_reference_is_allowed(self, mock_ui_root: Path) -> None:
        """Templates directory in legacy_flask_reference is allowed."""
        legacy_templates = mock_ui_root / "legacy_flask_reference" / "templates"
        legacy_templates.mkdir(parents=True)

        violations = check_templates_directory(mock_ui_root)

        assert violations == []

    def test_templates_file_not_directory_is_allowed(self, mock_ui_root: Path) -> None:
        """A file named 'templates' (not directory) should not trigger violation."""
        (mock_ui_root / "templates").touch()  # Create a file, not directory

        violations = check_templates_directory(mock_ui_root)

        assert violations == []


class TestCheckFlaskAppPatterns:
    """Tests for the check_flask_app_patterns function."""

    def test_no_app_py_returns_empty(self, mock_ui_root: Path) -> None:
        """UI without app.py should pass."""
        (mock_ui_root / "src").mkdir()
        (mock_ui_root / "src" / "main.tsx").touch()

        violations = check_flask_app_patterns(mock_ui_root)

        assert violations == []

    def test_fastapi_app_py_is_allowed(self, mock_ui_root: Path) -> None:
        """FastAPI app.py without Flask patterns should pass."""
        app_py = mock_ui_root / "app.py"
        app_py.write_text(
            '''"""FastAPI JSON API backend."""
from fastapi import FastAPI

app = FastAPI()

@app.get("/ui/health")
def health():
    return {"status": "ok"}
'''
        )

        violations = check_flask_app_patterns(mock_ui_root)

        assert violations == []

    def test_flask_import_is_violation(self, mock_ui_root: Path) -> None:
        """Flask import in app.py is a violation."""
        app_py = mock_ui_root / "app.py"
        app_py.write_text(
            '''"""Flask app."""
from flask import Flask, render_template

app = Flask(__name__)
'''
        )

        violations = check_flask_app_patterns(mock_ui_root)

        assert len(violations) == 1
        assert violations[0].rule == "NO_FLASK_APP_IN_UI"
        assert "from flask import" in violations[0].message

    def test_render_template_is_violation(self, mock_ui_root: Path) -> None:
        """render_template usage is a violation."""
        app_py = mock_ui_root / "app.py"
        app_py.write_text(
            '''"""App with template rendering."""
def index():
    return render_template("index.html")
'''
        )

        violations = check_flask_app_patterns(mock_ui_root)

        assert len(violations) == 1
        assert "render_template(" in violations[0].message

    def test_flask_app_in_legacy_reference_is_allowed(self, mock_ui_root: Path) -> None:
        """Flask app.py in legacy_flask_reference is allowed."""
        legacy = mock_ui_root / "legacy_flask_reference"
        legacy.mkdir()
        app_py = legacy / "app.py"
        app_py.write_text(
            '''"""Legacy Flask app."""
from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")
'''
        )

        violations = check_flask_app_patterns(mock_ui_root)

        assert violations == []

    def test_multiple_flask_indicators_all_reported(self, mock_ui_root: Path) -> None:
        """All Flask indicators in a file should be listed."""
        app_py = mock_ui_root / "app.py"
        app_py.write_text(
            '''"""Flask app with all indicators."""
from flask import Flask, render_template
import flask

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")
'''
        )

        violations = check_flask_app_patterns(mock_ui_root)

        assert len(violations) == 1
        # Check that multiple indicators are reported
        message = violations[0].message
        assert "from flask import" in message
        assert "Flask(__name__)" in message


class TestBoundaryViolation:
    """Tests for the BoundaryViolation named tuple."""

    def test_boundary_violation_fields(self, tmp_path: Path) -> None:
        """BoundaryViolation should have expected fields."""
        violation = BoundaryViolation(
            path=tmp_path / "test.py",
            rule="TEST_RULE",
            message="Test message",
        )

        assert violation.path == tmp_path / "test.py"
        assert violation.rule == "TEST_RULE"
        assert violation.message == "Test message"


class TestIntegration:
    """Integration tests for the full boundary check flow."""

    def test_clean_ui_directory_passes_all_checks(self, mock_ui_root: Path) -> None:
        """A properly structured UI directory should pass all checks."""
        # Create canonical React SPA structure
        src = mock_ui_root / "src"
        src.mkdir()
        (src / "App.tsx").touch()
        (src / "main.tsx").touch()

        components = src / "components"
        components.mkdir()
        (components / "Header.tsx").touch()

        # Run all checks
        python_violations = check_python_files(mock_ui_root)
        templates_violations = check_templates_directory(mock_ui_root)
        flask_violations = check_flask_app_patterns(mock_ui_root)

        assert python_violations == []
        assert templates_violations == []
        assert flask_violations == []

    def test_flask_project_structure_is_violation(self, mock_ui_root: Path) -> None:
        """A Flask-style project structure should trigger violations."""
        # Create Flask-style structure
        (mock_ui_root / "app.py").write_text("from flask import Flask\napp = Flask(__name__)")
        (mock_ui_root / "__init__.py").touch()
        templates = mock_ui_root / "templates"
        templates.mkdir()
        (templates / "base.html").touch()
        (templates / "index.html").touch()

        # Run all checks
        python_violations = check_python_files(mock_ui_root)
        templates_violations = check_templates_directory(mock_ui_root)
        flask_violations = check_flask_app_patterns(mock_ui_root)

        assert len(python_violations) == 2  # app.py and __init__.py
        assert len(templates_violations) == 1
        assert len(flask_violations) == 1

    def test_mixed_structure_with_legacy_reference(self, mock_ui_root: Path) -> None:
        """Legacy reference folder should be allowed alongside canonical UI."""
        # Create canonical React SPA
        src = mock_ui_root / "src"
        src.mkdir()
        (src / "App.tsx").touch()

        # Create legacy Flask reference (allowed)
        legacy = mock_ui_root / "legacy_flask_reference"
        legacy.mkdir()
        (legacy / "app.py").write_text("from flask import Flask\napp = Flask(__name__)")
        legacy_templates = legacy / "templates"
        legacy_templates.mkdir()
        (legacy_templates / "index.html").touch()

        # Run all checks
        python_violations = check_python_files(mock_ui_root)
        templates_violations = check_templates_directory(mock_ui_root)
        flask_violations = check_flask_app_patterns(mock_ui_root)

        # All violations should be empty - legacy reference is allowed
        assert python_violations == []
        assert templates_violations == []
        assert flask_violations == []


def test_vendor_python_is_not_application_code(tmp_path):
    ui=tmp_path/'apps'/'ui'
    vendor=ui/'node_modules'/'dependency'
    vendor.mkdir(parents=True)
    (vendor/'helper.py').write_text('pass')
    from scripts.ci.check_ui_boundary import check_python_files
    assert not check_python_files(ui)
    (ui/'application.py').write_text('pass')
    assert len(check_python_files(ui))==1
