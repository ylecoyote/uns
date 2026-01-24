"""Unit tests for the UI boundary guardrail script.

Tests cover:
- Detection of Python files outside legacy folder
- Detection of templates directories
- Detection of Flask app patterns
- Handling of missing directories
- Legacy folder exemption
- Command-line argument handling
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# Import from the script
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "ci"))
from check_ui_boundary import (
    BoundaryViolation,
    check_flask_app_patterns,
    check_python_files,
    check_templates_directory,
    find_repo_root,
    is_in_legacy_reference,
)


class TestFindRepoRoot:
    """Tests for find_repo_root function."""

    def test_finds_repo_root_from_script_location(self) -> None:
        """Should find repo root containing pyproject.toml."""
        repo_root = find_repo_root()
        assert repo_root.exists()
        assert (repo_root / "pyproject.toml").exists() or (repo_root / ".git").exists()

    def test_repo_root_contains_expected_structure(self) -> None:
        """Repo root should contain apps/ui directory."""
        repo_root = find_repo_root()
        ui_dir = repo_root / "apps" / "ui"
        assert ui_dir.exists(), f"apps/ui should exist at {ui_dir}"


class TestIsInLegacyReference:
    """Tests for is_in_legacy_reference function."""

    def test_path_in_legacy_folder_returns_true(self, tmp_path: Path) -> None:
        """Files in legacy_flask_reference should be exempted."""
        ui_root = tmp_path / "ui"
        legacy_dir = ui_root / "legacy_flask_reference"
        legacy_dir.mkdir(parents=True)
        legacy_file = legacy_dir / "old_app.py"
        legacy_file.touch()

        assert is_in_legacy_reference(legacy_file, ui_root) is True

    def test_path_outside_legacy_folder_returns_false(self, tmp_path: Path) -> None:
        """Files outside legacy_flask_reference should not be exempted."""
        ui_root = tmp_path / "ui"
        ui_root.mkdir(parents=True)
        regular_file = ui_root / "app.py"
        regular_file.touch()

        assert is_in_legacy_reference(regular_file, ui_root) is False

    def test_nested_path_in_legacy_folder(self, tmp_path: Path) -> None:
        """Deeply nested files in legacy folder should be exempted."""
        ui_root = tmp_path / "ui"
        legacy_dir = ui_root / "legacy_flask_reference" / "src" / "pages"
        legacy_dir.mkdir(parents=True)
        nested_file = legacy_dir / "routes.py"
        nested_file.touch()

        assert is_in_legacy_reference(nested_file, ui_root) is True


class TestCheckPythonFiles:
    """Tests for check_python_files function."""

    def test_empty_directory_returns_no_violations(self, tmp_path: Path) -> None:
        """Empty UI directory should have no violations."""
        ui_root = tmp_path / "ui"
        ui_root.mkdir()

        violations = check_python_files(ui_root)
        assert violations == []

    def test_typescript_files_are_allowed(self, tmp_path: Path) -> None:
        """TypeScript files should not trigger violations."""
        ui_root = tmp_path / "ui"
        src_dir = ui_root / "src"
        src_dir.mkdir(parents=True)

        (src_dir / "App.tsx").write_text("export default function App() {}")
        (src_dir / "main.ts").write_text("console.log('hello')")

        violations = check_python_files(ui_root)
        assert violations == []

    def test_python_files_in_root_trigger_violation(self, tmp_path: Path) -> None:
        """Python files in UI root should trigger violations."""
        ui_root = tmp_path / "ui"
        ui_root.mkdir()
        (ui_root / "app.py").write_text("# Python file")

        violations = check_python_files(ui_root)
        assert len(violations) == 1
        assert violations[0].rule == "NO_PYTHON_IN_CANONICAL_UI"
        assert "app.py" in str(violations[0].path)

    def test_python_files_in_subdirectory_trigger_violation(self, tmp_path: Path) -> None:
        """Python files in UI subdirectories should trigger violations."""
        ui_root = tmp_path / "ui"
        pages_dir = ui_root / "src" / "pages"
        pages_dir.mkdir(parents=True)
        (pages_dir / "routes.py").write_text("# Routes")

        violations = check_python_files(ui_root)
        assert len(violations) == 1
        assert "routes.py" in str(violations[0].path)

    def test_python_files_in_legacy_folder_are_exempted(self, tmp_path: Path) -> None:
        """Python files in legacy_flask_reference should be exempted."""
        ui_root = tmp_path / "ui"
        legacy_dir = ui_root / "legacy_flask_reference"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "old_app.py").write_text("# Old Flask app")
        (legacy_dir / "models.py").write_text("# Old models")

        violations = check_python_files(ui_root)
        assert violations == []

    def test_init_files_trigger_violation(self, tmp_path: Path) -> None:
        """__init__.py files should also trigger violations."""
        ui_root = tmp_path / "ui"
        ui_root.mkdir()
        (ui_root / "__init__.py").write_text("")

        violations = check_python_files(ui_root)
        assert len(violations) == 1
        assert "__init__.py" in str(violations[0].path)

    def test_nonexistent_directory_returns_no_violations(self, tmp_path: Path) -> None:
        """Nonexistent UI directory should return no violations."""
        ui_root = tmp_path / "nonexistent"

        violations = check_python_files(ui_root)
        assert violations == []


class TestCheckTemplatesDirectory:
    """Tests for check_templates_directory function."""

    def test_no_templates_directory_returns_no_violations(self, tmp_path: Path) -> None:
        """UI without templates directory should have no violations."""
        ui_root = tmp_path / "ui"
        ui_root.mkdir()

        violations = check_templates_directory(ui_root)
        assert violations == []

    def test_templates_directory_triggers_violation(self, tmp_path: Path) -> None:
        """Templates directory should trigger a violation."""
        ui_root = tmp_path / "ui"
        templates_dir = ui_root / "templates"
        templates_dir.mkdir(parents=True)

        violations = check_templates_directory(ui_root)
        assert len(violations) == 1
        assert violations[0].rule == "NO_TEMPLATES_DIRECTORY"

    def test_templates_in_subdirectory_triggers_violation(self, tmp_path: Path) -> None:
        """Templates directory anywhere in UI hierarchy should trigger violation."""
        ui_root = tmp_path / "ui"
        nested_templates = ui_root / "src" / "pages" / "templates"
        nested_templates.mkdir(parents=True)

        violations = check_templates_directory(ui_root)
        assert len(violations) == 1

    def test_templates_in_legacy_folder_are_exempted(self, tmp_path: Path) -> None:
        """Templates in legacy_flask_reference should be exempted."""
        ui_root = tmp_path / "ui"
        legacy_templates = ui_root / "legacy_flask_reference" / "templates"
        legacy_templates.mkdir(parents=True)

        violations = check_templates_directory(ui_root)
        assert violations == []

    def test_templates_file_not_directory_is_allowed(self, tmp_path: Path) -> None:
        """A file named 'templates' should not trigger violation."""
        ui_root = tmp_path / "ui"
        ui_root.mkdir()
        (ui_root / "templates").write_text("This is a file, not a directory")

        violations = check_templates_directory(ui_root)
        assert violations == []


class TestCheckFlaskAppPatterns:
    """Tests for check_flask_app_patterns function."""

    def test_fastapi_app_is_allowed(self, tmp_path: Path) -> None:
        """FastAPI apps without Flask patterns should not trigger violations."""
        ui_root = tmp_path / "ui"
        ui_root.mkdir()
        (ui_root / "app.py").write_text("""
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def index():
    return {"status": "ok"}
""")

        violations = check_flask_app_patterns(ui_root)
        assert violations == []

    def test_flask_import_triggers_violation(self, tmp_path: Path) -> None:
        """Flask imports should trigger violations."""
        ui_root = tmp_path / "ui"
        ui_root.mkdir()
        (ui_root / "app.py").write_text("""
from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")
""")

        violations = check_flask_app_patterns(ui_root)
        assert len(violations) == 1
        assert violations[0].rule == "NO_FLASK_APP_IN_UI"
        assert "Flask" in violations[0].message or "flask" in violations[0].message

    def test_render_template_triggers_violation(self, tmp_path: Path) -> None:
        """render_template calls should trigger violations."""
        ui_root = tmp_path / "ui"
        ui_root.mkdir()
        (ui_root / "app.py").write_text("""
from flask import render_template

def show_page():
    return render_template("page.html")
""")

        violations = check_flask_app_patterns(ui_root)
        assert len(violations) == 1

    def test_flask_in_legacy_folder_is_exempted(self, tmp_path: Path) -> None:
        """Flask apps in legacy_flask_reference should be exempted."""
        ui_root = tmp_path / "ui"
        legacy_dir = ui_root / "legacy_flask_reference"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "app.py").write_text("""
from flask import Flask, render_template
app = Flask(__name__)
""")

        violations = check_flask_app_patterns(ui_root)
        assert violations == []

    def test_nested_app_py_with_flask_triggers_violation(self, tmp_path: Path) -> None:
        """Nested app.py files with Flask should trigger violations."""
        ui_root = tmp_path / "ui"
        pages_dir = ui_root / "src" / "pages"
        pages_dir.mkdir(parents=True)
        (pages_dir / "app.py").write_text("from flask import Flask")

        violations = check_flask_app_patterns(ui_root)
        assert len(violations) == 1


class TestScriptIntegration:
    """Integration tests for the full script."""

    def test_script_runs_without_error(self) -> None:
        """Script should execute without crashing."""
        repo_root = find_repo_root()
        script_path = repo_root / "scripts" / "ci" / "check_ui_boundary.py"

        result = subprocess.run(
            [sys.executable, str(script_path), "--quiet"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )

        # Should complete (exit code 0 in non-strict, may have warnings)
        assert result.returncode == 0, f"Script failed: {result.stderr}"

    def test_strict_mode_exits_with_error_on_violations(self) -> None:
        """Strict mode should exit with error code 1 when violations exist."""
        # Run against real repo which has violations (Python files in apps/ui)
        repo_root = find_repo_root()
        script_path = repo_root / "scripts" / "ci" / "check_ui_boundary.py"

        result = subprocess.run(
            [sys.executable, str(script_path), "--strict", "--quiet"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )
        assert result.returncode == 1

    def test_help_flag_shows_usage(self) -> None:
        """--help should show usage information."""
        repo_root = find_repo_root()
        script_path = repo_root / "scripts" / "ci" / "check_ui_boundary.py"

        result = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "UI boundary" in result.stdout.lower() or "boundary" in result.stdout.lower()

    def test_fix_flag_shows_guidance(self) -> None:
        """--fix should show migration guidance."""
        repo_root = find_repo_root()
        script_path = repo_root / "scripts" / "ci" / "check_ui_boundary.py"

        result = subprocess.run(
            [sys.executable, str(script_path), "--fix"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )

        assert "Migration" in result.stdout or "migration" in result.stdout


class TestBoundaryViolation:
    """Tests for the BoundaryViolation named tuple."""

    def test_boundary_violation_creation(self, tmp_path: Path) -> None:
        """Should create a valid BoundaryViolation."""
        path = tmp_path / "test.py"
        violation = BoundaryViolation(
            path=path,
            rule="TEST_RULE",
            message="Test message",
        )

        assert violation.path == path
        assert violation.rule == "TEST_RULE"
        assert violation.message == "Test message"

    def test_boundary_violation_is_immutable(self, tmp_path: Path) -> None:
        """BoundaryViolation should be immutable (NamedTuple)."""
        path = tmp_path / "test.py"
        violation = BoundaryViolation(
            path=path,
            rule="TEST_RULE",
            message="Test message",
        )

        with pytest.raises(AttributeError):
            violation.rule = "NEW_RULE"  # type: ignore[misc]
