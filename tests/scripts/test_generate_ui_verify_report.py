"""Tests for UI verification report generator.

These tests verify that the report generator is:
1. Deterministic - same inputs produce identical outputs
2. Idempotent - running multiple times is safe
3. Atomic - partial writes don't corrupt files
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# Add scripts to path for import
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from verify.generate_ui_verify_report import (  # noqa: E402
    AtomicFileWriter,
    ReportGenerator,
    VerificationCheck,
    VerificationReport,
    create_phase_1_2_report,
    get_project_root,
    main,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def project_root():
    """Get the actual project root."""
    return get_project_root()


@pytest.fixture
def sample_report():
    """Create a sample verification report for testing."""
    return VerificationReport(
        phase="test",
        scope="Test Phase - Unit Tests",
        generated_date="2026-01-23",
        checks=[
            VerificationCheck(
                id="CHK-001",
                description="Sample check 1",
                status="PASS",
                evidence="Test evidence",
                section="Test Section",
            ),
            VerificationCheck(
                id="CHK-002",
                description="Sample check 2",
                status="FAIL",
                evidence="Failure evidence",
                section="Test Section",
            ),
        ],
        scope_limits_covered=["Item A", "Item B"],
        scope_limits_not_covered=["Item C"],
        unverifiable_claims=["Claim 1"],
    )


# =============================================================================
# Test: VerificationReport
# =============================================================================


class TestVerificationReport:
    """Tests for VerificationReport dataclass."""

    def test_overall_status_all_pass(self):
        """All PASS checks should result in PASS status."""
        report = VerificationReport(
            phase="1",
            scope="Test",
            generated_date="2026-01-23",
            checks=[
                VerificationCheck(id="1", description="A", status="PASS", section="S"),
                VerificationCheck(id="2", description="B", status="PASS", section="S"),
            ],
        )
        assert report.overall_status == "PASS"

    def test_overall_status_any_fail(self):
        """Any FAIL check should result in FAIL status."""
        report = VerificationReport(
            phase="1",
            scope="Test",
            generated_date="2026-01-23",
            checks=[
                VerificationCheck(id="1", description="A", status="PASS", section="S"),
                VerificationCheck(id="2", description="B", status="FAIL", section="S"),
            ],
        )
        assert report.overall_status == "FAIL"

    def test_overall_status_partial_with_skip(self):
        """SKIP without FAIL should result in PARTIAL status."""
        report = VerificationReport(
            phase="1",
            scope="Test",
            generated_date="2026-01-23",
            checks=[
                VerificationCheck(id="1", description="A", status="PASS", section="S"),
                VerificationCheck(id="2", description="B", status="SKIP", section="S"),
            ],
        )
        assert report.overall_status == "PARTIAL"

    def test_overall_status_no_checks(self):
        """No checks should result in NO_CHECKS status."""
        report = VerificationReport(
            phase="1",
            scope="Test",
            generated_date="2026-01-23",
        )
        assert report.overall_status == "NO_CHECKS"

    def test_counts(self, sample_report):
        """Test pass/fail/skip count properties."""
        assert sample_report.pass_count == 1
        assert sample_report.fail_count == 1
        assert sample_report.skip_count == 0


# =============================================================================
# Test: Determinism
# =============================================================================


class TestDeterminism:
    """Tests that report generation is deterministic."""

    def test_same_input_same_output(self, project_root, sample_report):
        """Same report data should produce identical markdown output."""
        generator = ReportGenerator(project_root)

        output1 = generator.generate_report(sample_report)
        output2 = generator.generate_report(sample_report)

        assert output1 == output2

    def test_report_hash_is_stable(self, project_root, sample_report):
        """Report hash should be identical for identical reports."""
        generator = ReportGenerator(project_root)

        output = generator.generate_report(sample_report)
        lines = output.strip().split("\n")

        # Find hash line
        hash_lines = [line for line in lines if line.startswith("*Report hash:")]
        assert len(hash_lines) == 1

        # Generate again and compare
        output2 = generator.generate_report(sample_report)
        lines2 = output2.strip().split("\n")
        hash_lines2 = [line for line in lines2 if line.startswith("*Report hash:")]

        assert hash_lines[0] == hash_lines2[0]

    def test_checks_sorted_by_id(self, project_root):
        """Checks should be sorted by ID for deterministic output."""
        report = VerificationReport(
            phase="1",
            scope="Test",
            generated_date="2026-01-23",
            checks=[
                VerificationCheck(id="CHK-003", description="C", status="PASS", section="S"),
                VerificationCheck(id="CHK-001", description="A", status="PASS", section="S"),
                VerificationCheck(id="CHK-002", description="B", status="PASS", section="S"),
            ],
        )

        generator = ReportGenerator(project_root)
        output = generator.generate_report(report)

        # Find order in checklist table
        lines = output.split("\n")
        checklist_lines = [line for line in lines if line.startswith("| CHK-")]

        # Extract IDs
        ids = [line.split("|")[1].strip().split(":")[0] for line in checklist_lines]

        # Note: The checks are sorted by description for the checklist, but IDs should appear in order
        assert ids == sorted(ids)


# =============================================================================
# Test: Idempotency
# =============================================================================


class TestIdempotency:
    """Tests that report generation is idempotent."""

    def test_overwrite_produces_same_content(self, temp_dir, project_root, sample_report):
        """Writing to existing file should produce same content."""
        output_path = temp_dir / "report.md"
        generator = ReportGenerator(project_root)

        # Write first time
        content1 = generator.generate_report(sample_report)
        output_path.write_text(content1)

        # Write second time (simulating rerun)
        content2 = generator.generate_report(sample_report)
        output_path.write_text(content2)

        assert output_path.read_text() == content1
        assert content1 == content2

    def test_main_with_existing_file_no_force(self, temp_dir, project_root):
        """Running with existing file without --force should succeed."""
        output_path = temp_dir / "phase-test-verify.md"
        output_path.write_text("existing content")

        with mock.patch(
            "verify.generate_ui_verify_report.get_project_root",
            return_value=project_root,
        ):
            result = main(["--phase", "1.2", "--output", str(output_path)])

        # Should succeed (idempotent - existing file is fine)
        assert result == 0
        # Should not overwrite
        assert output_path.read_text() == "existing content"

    def test_main_with_force_overwrites(self, temp_dir, project_root):
        """Running with --force should overwrite existing file."""
        output_path = temp_dir / "phase-1.2-verify.md"
        output_path.write_text("existing content")

        with mock.patch(
            "verify.generate_ui_verify_report.get_project_root",
            return_value=project_root,
        ):
            result = main(["--phase", "1.2", "--output", str(output_path), "--force"])

        # Should succeed
        assert result in [0, 1]  # 0 for pass, 1 for fail (but report generated)
        # Should overwrite with new content
        assert output_path.read_text() != "existing content"


# =============================================================================
# Test: Atomic Writing
# =============================================================================


class TestAtomicWriting:
    """Tests for atomic file writing."""

    def test_atomic_write_creates_file(self, temp_dir, caplog):
        """AtomicFileWriter should create new file atomically."""
        import logging

        logger = logging.getLogger("test")
        output_path = temp_dir / "test_report.md"
        writer = AtomicFileWriter(output_path, logger)

        content = "# Test Report\n\nContent here."
        writer.write(content)

        assert output_path.exists()
        assert output_path.read_text() == content

    def test_atomic_write_overwrites_existing(self, temp_dir, caplog):
        """AtomicFileWriter should overwrite existing file."""
        import logging

        logger = logging.getLogger("test")
        output_path = temp_dir / "test_report.md"
        output_path.write_text("old content")

        writer = AtomicFileWriter(output_path, logger)
        content = "# New Report\n\nNew content here."
        writer.write(content)

        assert output_path.read_text() == content

    def test_atomic_write_no_partial_on_failure(self, temp_dir, caplog):
        """AtomicFileWriter should not leave partial file on failure."""
        import logging

        logger = logging.getLogger("test")
        output_path = temp_dir / "subdir" / "test_report.md"

        # Create parent directory
        output_path.parent.mkdir(parents=True)

        # Write initial content
        output_path.write_text("original content")

        # Mock os.fsync to raise an exception during write
        writer = AtomicFileWriter(output_path, logger)

        with mock.patch("os.fsync", side_effect=OSError("Disk full")), pytest.raises(
            OSError
        ):
            writer.write("new content")

        # Original file should be unchanged
        assert output_path.read_text() == "original content"

    def test_atomic_write_creates_parent_dirs(self, temp_dir):
        """AtomicFileWriter should create parent directories."""
        import logging

        logger = logging.getLogger("test")
        output_path = temp_dir / "a" / "b" / "c" / "report.md"

        writer = AtomicFileWriter(output_path, logger)
        writer.write("content")

        assert output_path.exists()
        assert output_path.read_text() == "content"


# =============================================================================
# Test: Report Content
# =============================================================================


class TestReportContent:
    """Tests for generated report content."""

    def test_report_has_required_sections(self, project_root, sample_report):
        """Generated report should have all required sections."""
        generator = ReportGenerator(project_root)
        output = generator.generate_report(sample_report)

        required_sections = [
            "# UI Phase",
            "## Executive Summary",
            "## Scope Limits",
            "## Verification Checklist",
            "## Conclusion",
        ]

        for section in required_sections:
            assert section in output, f"Missing section: {section}"

    def test_report_includes_all_checks(self, project_root, sample_report):
        """All checks should appear in the report."""
        generator = ReportGenerator(project_root)
        output = generator.generate_report(sample_report)

        for check in sample_report.checks:
            assert check.id in output
            assert check.description in output

    def test_report_shows_status_correctly(self, project_root, sample_report):
        """Report should show correct status for each check."""
        generator = ReportGenerator(project_root)
        output = generator.generate_report(sample_report)

        # PASS check should show ✅
        assert "✅ PASS" in output
        # FAIL check should show ❌
        assert "❌ FAIL" in output

    def test_report_date_is_date_only(self, project_root, sample_report):
        """Generated date should be date only (no time) for determinism."""
        generator = ReportGenerator(project_root)
        output = generator.generate_report(sample_report)

        # Date format should be YYYY-MM-DD only
        assert "**Generated**: 2026-01-23" in output
        # Should not contain time components
        assert "T" not in output.split("**Generated**:")[1].split("\n")[0]


# =============================================================================
# Test: Phase 1.2 Specific Checks
# =============================================================================


class TestPhase12Report:
    """Tests for Phase 1.2 verification report."""

    def test_phase_1_2_report_has_expected_checks(self, project_root):
        """Phase 1.2 report should verify guardrails, CI, and contracts."""
        report = create_phase_1_2_report(project_root)

        check_ids = {c.id for c in report.checks}

        # Should have checks for key areas
        expected_prefixes = ["CHK-GUARD", "CHK-CI", "CHK-CONTRACT", "CHK-REPORT"]
        for prefix in expected_prefixes:
            matching = [cid for cid in check_ids if cid.startswith(prefix)]
            assert len(matching) > 0, f"No checks with prefix {prefix}"

    def test_phase_1_2_scope_covers_guardrails(self, project_root):
        """Phase 1.2 scope should mention guardrails."""
        report = create_phase_1_2_report(project_root)

        covered_text = " ".join(report.scope_limits_covered)
        assert "guardrail" in covered_text.lower() or "boundary" in covered_text.lower()

    def test_phase_1_2_scope_covers_contracts(self, project_root):
        """Phase 1.2 scope should mention contracts."""
        report = create_phase_1_2_report(project_root)

        covered_text = " ".join(report.scope_limits_covered)
        assert "contract" in covered_text.lower()


# =============================================================================
# Test: CLI Interface
# =============================================================================


class TestCLI:
    """Tests for command-line interface."""

    def test_dry_run_prints_to_stdout(self, capsys, project_root):
        """--dry-run should print report to stdout."""
        with mock.patch(
            "verify.generate_ui_verify_report.get_project_root",
            return_value=project_root,
        ):
            result = main(["--phase", "1.2", "--dry-run"])

        captured = capsys.readouterr()
        assert "# UI Phase 1.2" in captured.out
        assert result == 0

    def test_missing_phase_fails(self):
        """Missing --phase should fail."""
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 2

    def test_output_path_can_be_specified(self, temp_dir, project_root):
        """--output should allow custom output path."""
        output_path = temp_dir / "custom" / "report.md"

        with mock.patch(
            "verify.generate_ui_verify_report.get_project_root",
            return_value=project_root,
        ):
            result = main(["--phase", "1.2", "--output", str(output_path)])

        assert result in [0, 1]
        assert output_path.exists()


# =============================================================================
# Test: Logging
# =============================================================================


class TestLogging:
    """Tests for logging behavior."""

    def test_log_file_created_on_run(self, temp_dir, project_root):  # noqa: ARG002
        """Log file should be created in _logs directory."""
        output_path = temp_dir / "report.md"

        # Create a mock project root with _logs dir
        mock_root = temp_dir
        (mock_root / "docs" / "reports" / "ui" / "_logs").mkdir(parents=True)
        (mock_root / "pyproject.toml").touch()

        with mock.patch(
            "verify.generate_ui_verify_report.get_project_root",
            return_value=mock_root,
        ):
            main(["--phase", "1.2", "--output", str(output_path)])

        # Log file should exist
        log_file = mock_root / "docs" / "reports" / "ui" / "_logs" / "phase-1.2-verify.log"
        assert log_file.exists()


# =============================================================================
# Test: Error Handling
# =============================================================================


class TestErrorHandling:
    """Tests for error handling."""

    def test_returns_2_on_exception(self, temp_dir, project_root):
        """Script should return 2 on unexpected error."""
        with mock.patch(
            "verify.generate_ui_verify_report.get_project_root",
            side_effect=Exception("Unexpected error"),
        ):
            result = main(["--phase", "1.2", "--dry-run"])

        assert result == 2

    def test_returns_1_on_verification_failure(self, temp_dir, project_root):
        """Script should return 1 when verification has failures."""
        output_path = temp_dir / "report.md"

        # Create a mock project that will fail some checks
        mock_root = temp_dir / "project"
        mock_root.mkdir()
        (mock_root / "pyproject.toml").touch()
        # Don't create the expected files, so checks will fail

        with mock.patch(
            "verify.generate_ui_verify_report.get_project_root",
            return_value=mock_root,
        ):
            result = main(["--phase", "1.2", "--output", str(output_path)])

        assert result == 1
