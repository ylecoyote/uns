#!/usr/bin/env python3
"""UI Boundary Guardrail.

This script enforces the canonical UI boundary: apps/ui should contain only
React/TypeScript/Vite frontend code. Python files are not permitted in the
canonical UI directory structure.

Purpose:
    Prevent Flask/Python HTML-serving patterns from returning to the UI layer.
    The canonical UI is a React SPA served by Vite, with a separate JSON API
    backend in src/agsignal/api/routes_ui.py.

Rules:
    1. No .py files anywhere under apps/ui/** EXCEPT apps/ui/legacy_flask_reference/**
    2. No templates/ directories under apps/ui/** (Flask-style HTML templating)
    3. No app.py files under apps/ui/** EXCEPT apps/ui/legacy_flask_reference/**

Exit Codes:
    0 - All boundary rules satisfied
    1 - Boundary violations detected

Usage:
    python scripts/ci/check_ui_boundary.py
    python scripts/ci/check_ui_boundary.py --strict  # Fail on any violation
    python scripts/ci/check_ui_boundary.py --fix     # Show migration guidance

See also:
    - apps/ui/README.md (Boundary Rules section)
    - docs/ui/ui-scope.md (UI design philosophy)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import NamedTuple


class BoundaryViolation(NamedTuple):
    """Represents a UI boundary violation."""

    path: Path
    rule: str
    message: str


# Paths relative to repository root
UI_ROOT = Path("apps/ui")
LEGACY_REFERENCE_PATH = UI_ROOT / "legacy_flask_reference"


def find_repo_root() -> Path:
    """Find the repository root by looking for pyproject.toml or .git."""
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
            return parent
    # Fallback to script's grandparent (scripts/ci -> repo root)
    return Path(__file__).resolve().parent.parent.parent


def is_in_legacy_reference(path: Path, ui_root: Path) -> bool:
    """Check if a path is within the legacy_flask_reference directory."""
    legacy_path = ui_root / "legacy_flask_reference"
    try:
        path.relative_to(legacy_path)
        return True
    except ValueError:
        return False


def is_generated_or_vendor(path: Path, ui_root: Path) -> bool:
    """Dependencies and build outputs are not application source."""
    return any(part in {"node_modules", "dist", "coverage", "test-results"}
               for part in path.relative_to(ui_root).parts)


def check_python_files(ui_root: Path) -> list[BoundaryViolation]:
    """Check for Python files outside the legacy reference folder.

    Args:
        ui_root: Absolute path to apps/ui directory

    Returns:
        List of violations found
    """
    violations: list[BoundaryViolation] = []

    if not ui_root.exists():
        return violations

    for py_file in ui_root.rglob("*.py"):
        # Skip if in legacy_flask_reference
        if is_in_legacy_reference(py_file, ui_root) or is_generated_or_vendor(py_file, ui_root):
            continue

        # This is a violation
        violations.append(
            BoundaryViolation(
                path=py_file,
                rule="NO_PYTHON_IN_CANONICAL_UI",
                message=(
                    f"Python file found in canonical UI: {py_file.relative_to(ui_root.parent.parent)}\n"
                    "  The canonical apps/ui directory should contain only React/TypeScript/Vite code.\n"
                    "  Python backend code should live in src/agsignal/api/ or src/notification/."
                ),
            )
        )

    return violations


def check_templates_directory(ui_root: Path) -> list[BoundaryViolation]:
    """Check for Flask-style templates directories.

    Args:
        ui_root: Absolute path to apps/ui directory

    Returns:
        List of violations found
    """
    violations: list[BoundaryViolation] = []

    if not ui_root.exists():
        return violations

    for item in ui_root.rglob("templates"):
        if not item.is_dir():
            continue

        # Skip if in legacy_flask_reference
        if is_in_legacy_reference(item, ui_root) or is_generated_or_vendor(item, ui_root):
            continue

        violations.append(
            BoundaryViolation(
                path=item,
                rule="NO_TEMPLATES_DIRECTORY",
                message=(
                    f"Flask-style templates directory found: {item.relative_to(ui_root.parent.parent)}\n"
                    "  The canonical UI uses React components, not server-side HTML templates.\n"
                    "  Remove this directory or move it to apps/ui/legacy_flask_reference/."
                ),
            )
        )

    return violations


def check_flask_app_patterns(ui_root: Path) -> list[BoundaryViolation]:
    """Check for Flask app.py patterns that serve HTML.

    This is a more nuanced check - app.py itself might exist for FastAPI JSON API,
    but we want to ensure it's not serving HTML templates.

    Args:
        ui_root: Absolute path to apps/ui directory

    Returns:
        List of violations found
    """
    violations: list[BoundaryViolation] = []

    if not ui_root.exists():
        return violations

    for app_file in ui_root.rglob("app.py"):
        # Skip if in legacy_flask_reference
        if is_in_legacy_reference(app_file, ui_root) or is_generated_or_vendor(app_file, ui_root):
            continue

        # Check file contents for Flask indicators
        try:
            content = app_file.read_text(encoding="utf-8")

            # Check for Flask imports
            flask_indicators = [
                "from flask import",
                "import flask",
                "render_template(",
                "render_template_string(",
                "@app.route",
                "Flask(__name__)",
            ]

            found_indicators = [ind for ind in flask_indicators if ind in content]

            if found_indicators:
                violations.append(
                    BoundaryViolation(
                        path=app_file,
                        rule="NO_FLASK_APP_IN_UI",
                        message=(
                            f"Flask patterns found in: {app_file.relative_to(ui_root.parent.parent)}\n"
                            f"  Detected indicators: {', '.join(found_indicators)}\n"
                            "  The canonical UI should not use Flask for HTML serving.\n"
                            "  Use React components for UI, FastAPI for JSON API only."
                        ),
                    )
                )
        except (OSError, UnicodeDecodeError) as e:
            # Can't read file, skip
            print(f"Warning: Could not read {app_file}: {e}", file=sys.stderr)

    return violations


def format_violation(violation: BoundaryViolation, repo_root: Path) -> str:
    """Format a violation for display.

    Args:
        violation: The violation to format
        repo_root: Repository root path for relative path display

    Returns:
        Formatted string
    """
    try:
        rel_path = violation.path.relative_to(repo_root)
    except ValueError:
        rel_path = violation.path

    return f"""
[{violation.rule}]
File: {rel_path}
{violation.message}
"""


def show_migration_guidance() -> None:
    """Print migration guidance for addressing violations."""
    print(
        """
UI Boundary Migration Guidance
==============================

If you have Python files in apps/ui/ that need to be migrated:

1. Backend API Routes:
   Move to: src/agsignal/api/routes_ui.py
   The UI endpoints (/ui/*) are served from the main MCP server.

2. Pydantic Models/Types:
   Move to: src/notification/models.py or src/agsignal/api/read_models.py
   API response types should be defined in the backend, not the UI.

3. Test Files:
   Move to: tests/ui_client/ or tests/docs/
   Backend tests don't belong in the frontend package.

4. Reference Code (temporary):
   Move to: apps/ui/legacy_flask_reference/
   If you need to preserve old code for reference during migration.

5. Static Assets:
   Keep in: apps/ui/static/ (CSS, images, etc.)
   Or: apps/ui/public/ (Vite public assets)

For questions, see docs/ui/ui-scope.md for the canonical UI architecture.
"""
    )


def main() -> int:
    """Run UI boundary checks.

    Returns:
        Exit code (0 = success, 1 = violations found)
    """
    parser = argparse.ArgumentParser(
        description="Check UI boundary rules for the canonical apps/ui directory.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/ci/check_ui_boundary.py           # Run all checks
  python scripts/ci/check_ui_boundary.py --strict  # Fail on any violation
  python scripts/ci/check_ui_boundary.py --fix     # Show migration guidance
        """,
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with error on any violation (for CI enforcement)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Show migration guidance for fixing violations",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only output violations, no header/footer",
    )
    args = parser.parse_args()

    repo_root = find_repo_root()
    ui_root = repo_root / UI_ROOT

    if not args.quiet:
        print("=" * 60)
        print("UI Boundary Guardrail")
        print("=" * 60)
        print(f"Checking: {ui_root.relative_to(repo_root)}")
        print()

    # Run all checks
    all_violations: list[BoundaryViolation] = []

    # Check 1: Python files
    python_violations = check_python_files(ui_root)
    all_violations.extend(python_violations)

    # Check 2: Templates directories
    templates_violations = check_templates_directory(ui_root)
    all_violations.extend(templates_violations)

    # Check 3: Flask app patterns
    flask_violations = check_flask_app_patterns(ui_root)
    all_violations.extend(flask_violations)

    # Report results
    if all_violations:
        print(f"Found {len(all_violations)} boundary violation(s):\n")

        for violation in all_violations:
            print(format_violation(violation, repo_root))

        if args.fix:
            show_migration_guidance()

        if not args.quiet:
            print("-" * 60)
            print("Summary:")
            print(f"  Python files outside legacy: {len(python_violations)}")
            print(f"  Templates directories: {len(templates_violations)}")
            print(f"  Flask patterns: {len(flask_violations)}")
            print()

            if args.strict:
                print("FAILED: Boundary violations detected (--strict mode)")
                return 1
            else:
                print(
                    "WARNING: Boundary violations detected.\n"
                    "  Use --strict to enforce in CI.\n"
                    "  Use --fix for migration guidance."
                )
                # Return success in non-strict mode (warning only)
                return 0
    else:
        if not args.quiet:
            print("All boundary rules satisfied.")
            print()
            if ui_root.exists():
                # Count what's there
                py_count = len(list(ui_root.rglob("*.py")))
                ts_count = len(list(ui_root.rglob("*.ts"))) + len(list(ui_root.rglob("*.tsx")))
                print(f"  TypeScript/TSX files: {ts_count}")
                print(f"  Python files: {py_count}")
                if py_count > 0:
                    legacy_count = (
                        len(list((ui_root / "legacy_flask_reference").rglob("*.py")))
                        if (ui_root / "legacy_flask_reference").exists()
                        else 0
                    )
                    print(f"    (in legacy_flask_reference: {legacy_count})")

    return 1 if (args.strict and all_violations) else 0


if __name__ == "__main__":
    sys.exit(main())
