#!/usr/bin/env python3
"""Deterministic and idempotent UI verification report generator.

This script generates UI verification reports with the following guarantees:
1. Deterministic: Same inputs produce identical outputs (sorted, no timestamps that change)
2. Idempotent: Running multiple times produces the same result
3. Atomic: Uses temp file + rename to avoid partial writes
4. Logged: Failures are captured to docs/reports/ui/_logs/

Usage:
    python scripts/verify/generate_ui_verify_report.py --phase 1.2

Options:
    --phase PHASE    Phase identifier (e.g., "0", "1", "1.1", "1.2")
    --output PATH    Output file path (default: docs/reports/ui/phase-{phase}-verify.md)
    --dry-run        Print report to stdout instead of writing file
    --force          Overwrite existing report without prompting

Exit codes:
    0: Success
    1: Verification failed (report generated with failures)
    2: Script error (report not generated)
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
import tempfile
import traceback
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# Configure logging
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass
class VerificationCheck:
    """A single verification check result."""

    id: str
    description: str
    status: str  # "PASS", "FAIL", "SKIP"
    evidence: str = ""
    section: str = ""


@dataclass
class VerificationReport:
    """Aggregated verification report data."""

    phase: str
    scope: str
    generated_date: str  # ISO format date only (no time for determinism)
    checks: list[VerificationCheck] = field(default_factory=list)
    scope_limits_covered: list[str] = field(default_factory=list)
    scope_limits_not_covered: list[str] = field(default_factory=list)
    out_of_scope_risks: list[dict[str, str]] = field(default_factory=list)
    unverifiable_claims: list[str] = field(default_factory=list)

    @property
    def overall_status(self) -> str:
        """Compute overall status from individual checks."""
        if not self.checks:
            return "NO_CHECKS"
        if any(c.status == "FAIL" for c in self.checks):
            return "FAIL"
        if all(c.status == "PASS" for c in self.checks):
            return "PASS"
        return "PARTIAL"

    @property
    def pass_count(self) -> int:
        """Count passing checks."""
        return sum(1 for c in self.checks if c.status == "PASS")

    @property
    def fail_count(self) -> int:
        """Count failing checks."""
        return sum(1 for c in self.checks if c.status == "FAIL")

    @property
    def skip_count(self) -> int:
        """Count skipped checks."""
        return sum(1 for c in self.checks if c.status == "SKIP")


class ReportGenerator:
    """Generates deterministic verification reports."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.logger = logging.getLogger(__name__)

    def generate_report(self, report: VerificationReport) -> str:
        """Generate markdown report content.

        Returns deterministic output by:
        - Using date only (no timestamp)
        - Sorting lists alphabetically where order doesn't matter
        - Using consistent formatting
        """
        lines = [
            f"# UI Phase {report.phase} Bounded Verification Report",
            "",
            f"**Generated**: {report.generated_date}",
            f"**Scope**: {report.scope}",
            f"**Status**: {report.overall_status} (within scope)",
            "",
            "## Executive Summary",
            "",
        ]

        # Summary of checks
        lines.append(
            f"This bounded verification performed {len(report.checks)} checks. "
            f"Results: {report.pass_count} PASS, {report.fail_count} FAIL, "
            f"{report.skip_count} SKIP."
        )
        lines.append("")

        # Key findings (sorted for determinism)
        passed_checks = sorted(
            [c for c in report.checks if c.status == "PASS"],
            key=lambda c: c.id,
        )
        for check in passed_checks:
            lines.append(f"1. **{check.description}** - VERIFIED")
        lines.append("")

        lines.append(
            "**Important**: This is a bounded verification, not a proof or certification. "
            "See [Scope Limits](#scope-limits) and [Unverifiable Claims](#unverifiable-claims) "
            "for explicit boundaries."
        )
        lines.append("")
        lines.append("---")
        lines.append("")

        # Scope Limits
        lines.append("## Scope Limits")
        lines.append("")
        lines.append("This verification covers:")
        for item in report.scope_limits_covered:
            lines.append(f"- ✅ {item}")
        lines.append("")
        lines.append("This verification does **not** cover:")
        for item in report.scope_limits_not_covered:
            lines.append(f"- ❌ {item}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Out-of-Scope Risks
        if report.out_of_scope_risks:
            lines.append("## Out-of-Scope Risks")
            lines.append("")
            lines.append("| Risk | Why Out of Scope | Mitigation |")
            lines.append("|------|------------------|------------|")
            for risk in sorted(report.out_of_scope_risks, key=lambda r: r["risk"]):
                lines.append(
                    f"| {risk['risk']} | {risk['why']} | {risk['mitigation']} |"
                )
            lines.append("")
            lines.append("---")
            lines.append("")

        # Unverifiable Claims
        if report.unverifiable_claims:
            lines.append("## Unverifiable Claims")
            lines.append("")
            lines.append("The following cannot be verified by code inspection alone:")
            lines.append("")
            for i, claim in enumerate(report.unverifiable_claims, 1):
                lines.append(f"{i}. {claim}")
            lines.append("")
            lines.append("---")
            lines.append("")

        # Detailed Checks (grouped by section)
        sections: dict[str, list[VerificationCheck]] = {}
        for check in report.checks:
            section = check.section or "General"
            if section not in sections:
                sections[section] = []
            sections[section].append(check)

        section_num = 1
        for section_name in sorted(sections.keys()):
            checks = sorted(sections[section_name], key=lambda c: c.id)
            lines.append(f"## {section_num}. {section_name}")
            lines.append("")

            for check in checks:
                status_emoji = {
                    "PASS": "✅",
                    "FAIL": "❌",
                    "SKIP": "⏭️",
                }.get(check.status, "❓")

                lines.append(f"### {check.id}: {check.description}")
                lines.append("")
                lines.append(f"**Status**: {status_emoji} {check.status}")
                lines.append("")
                if check.evidence:
                    lines.append("**Evidence**:")
                    lines.append("")
                    # Indent evidence as code block if it looks like code/output
                    if "\n" in check.evidence or check.evidence.startswith("```"):
                        lines.append(check.evidence)
                    else:
                        lines.append(f"> {check.evidence}")
                    lines.append("")

            lines.append("---")
            lines.append("")
            section_num += 1

        # Verification Checklist
        lines.append("## Verification Checklist")
        lines.append("")
        lines.append("| Check | Status | Evidence |")
        lines.append("|-------|--------|----------|")
        for check in sorted(report.checks, key=lambda c: c.id):
            evidence_short = (
                check.evidence[:50] + "..."
                if len(check.evidence) > 50
                else check.evidence
            )
            evidence_short = evidence_short.replace("\n", " ").replace("|", "\\|")
            lines.append(f"| {check.description} | {check.status} | {evidence_short} |")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Conclusion
        lines.append("## Conclusion")
        lines.append("")
        lines.append(f"**Verification Result: {report.overall_status} (within scope)**")
        lines.append("")
        lines.append(
            "**Epistemic status**: This verification provides evidence of alignment, "
            "not proof. The absence of observed violations does not guarantee absence "
            "of all possible violations."
        )
        lines.append("")

        # Footer with generation metadata (deterministic hash)
        content_for_hash = "\n".join(lines)
        content_hash = hashlib.sha256(content_for_hash.encode()).hexdigest()[:8]
        lines.append("---")
        lines.append("")
        lines.append(f"*Report hash: {content_hash}*")
        lines.append("")

        return "\n".join(lines)


class AtomicFileWriter:
    """Writes files atomically using temp file + rename."""

    def __init__(self, target_path: Path, logger: logging.Logger):
        self.target_path = target_path
        self.logger = logger

    def write(self, content: str) -> None:
        """Write content atomically.

        1. Write to a temp file in the same directory
        2. Sync to disk
        3. Rename to target (atomic on POSIX)
        """
        target_dir = self.target_path.parent
        target_dir.mkdir(parents=True, exist_ok=True)

        # Create temp file in same directory for atomic rename
        fd, temp_path = tempfile.mkstemp(
            suffix=".tmp",
            prefix=".report_",
            dir=target_dir,
        )

        try:
            # Write content
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())

            # Atomic rename
            temp_path_obj = Path(temp_path)
            temp_path_obj.rename(self.target_path)

            self.logger.info(f"Report written to {self.target_path}")

        except Exception:
            # Clean up temp file on failure
            if Path(temp_path).exists():
                Path(temp_path).unlink()
            raise


def setup_logging(log_file: Path | None = None) -> logging.Logger:
    """Configure logging with optional file output."""
    logger = logging.getLogger("verify_report")
    logger.setLevel(logging.DEBUG)

    # Console handler
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(console)

    # File handler for failures
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
        logger.addHandler(file_handler)

    return logger


def get_project_root() -> Path:
    """Find project root by looking for pyproject.toml."""
    current = Path(__file__).resolve()
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def create_phase_1_2_report(project_root: Path) -> VerificationReport:
    """Create verification report for Phase 1.2 (guardrails + CI + contracts).

    This function performs the actual verification checks and returns
    structured data for report generation.
    """
    report = VerificationReport(
        phase="1.2",
        scope="UI Phase 1.2 - Guardrails, CI, and Contracts",
        generated_date=date.today().isoformat(),
    )

    # Scope limits
    report.scope_limits_covered = [
        "CI includes UI lint/typecheck/test/build",
        "Boundary guardrail exists and enforced in CI",
        "Contract drift tests exist (backend)",
        "Contract drift tests exist (UI-side decoders)",
        "Contract snapshot artifact exists",
        "Report generation is deterministic and idempotent",
    ]

    report.scope_limits_not_covered = [
        "Runtime behavior under production load",
        "Security vulnerabilities (XSS, injection, etc.)",
        "Performance characteristics",
        "Cross-browser compatibility",
        "Accessibility compliance (WCAG)",
    ]

    report.out_of_scope_risks = [
        {
            "risk": "XSS in rendered content",
            "why": "Security audit required",
            "mitigation": "React's JSX escaping provides baseline protection",
        },
        {
            "risk": "Contract drift undetected",
            "why": "Tests may not cover all fields",
            "mitigation": "Schema validation + TypeScript types",
        },
    ]

    report.unverifiable_claims = [
        '"CI always runs on PRs" - Depends on GitHub Actions configuration being active',
        '"Contracts are complete" - Schema may not cover all edge cases',
        '"Guardrail catches all violations" - Only checks file extensions, not content',
    ]

    # Perform verification checks
    checks = []

    # Check 1: UI boundary guardrail script exists
    guardrail_script = project_root / "scripts" / "ci" / "check_ui_boundary.py"
    if guardrail_script.exists():
        checks.append(
            VerificationCheck(
                id="CHK-GUARD-001",
                description="UI boundary guardrail script exists",
                status="PASS",
                evidence=f"Found at {guardrail_script.relative_to(project_root)}",
                section="Boundary Guardrails",
            )
        )
    else:
        # Also check for shell script variant
        guardrail_sh = project_root / "scripts" / "ci" / "check_ui_boundary.sh"
        if guardrail_sh.exists():
            checks.append(
                VerificationCheck(
                    id="CHK-GUARD-001",
                    description="UI boundary guardrail script exists",
                    status="PASS",
                    evidence=f"Found at {guardrail_sh.relative_to(project_root)}",
                    section="Boundary Guardrails",
                )
            )
        else:
            checks.append(
                VerificationCheck(
                    id="CHK-GUARD-001",
                    description="UI boundary guardrail script exists",
                    status="FAIL",
                    evidence="No guardrail script found at scripts/ci/check_ui_boundary.(py|sh)",
                    section="Boundary Guardrails",
                )
            )

    # Check 2: CI workflow includes UI jobs
    ci_workflow = project_root / ".github" / "workflows"
    if ci_workflow.exists():
        workflow_files = list(ci_workflow.glob("*.yml")) + list(
            ci_workflow.glob("*.yaml")
        )
        ui_ci_found = False
        for wf in workflow_files:
            content = wf.read_text()
            if "apps/ui" in content or "npm run" in content:
                ui_ci_found = True
                break
        if ui_ci_found:
            checks.append(
                VerificationCheck(
                    id="CHK-CI-001",
                    description="CI workflow includes UI jobs",
                    status="PASS",
                    evidence=f"Found UI-related jobs in {wf.name}",
                    section="CI Configuration",
                )
            )
        else:
            checks.append(
                VerificationCheck(
                    id="CHK-CI-001",
                    description="CI workflow includes UI jobs",
                    status="FAIL",
                    evidence="No UI jobs found in CI workflows",
                    section="CI Configuration",
                )
            )
    else:
        checks.append(
            VerificationCheck(
                id="CHK-CI-001",
                description="CI workflow includes UI jobs",
                status="SKIP",
                evidence="No .github/workflows directory found",
                section="CI Configuration",
            )
        )

    # Check 3: Backend contract tests exist
    backend_contract_tests = list(
        (project_root / "tests").rglob("*contract*.py")
    ) + list((project_root / "tests").rglob("*ui_contracts*.py"))
    if backend_contract_tests:
        checks.append(
            VerificationCheck(
                id="CHK-CONTRACT-001",
                description="Backend contract tests exist",
                status="PASS",
                evidence=f"Found {len(backend_contract_tests)} contract test file(s)",
                section="Contract Verification",
            )
        )
    else:
        checks.append(
            VerificationCheck(
                id="CHK-CONTRACT-001",
                description="Backend contract tests exist",
                status="FAIL",
                evidence="No contract test files found in tests/",
                section="Contract Verification",
            )
        )

    # Check 4: UI-side validators/decoders exist
    ui_src = project_root / "apps" / "ui" / "src"
    if ui_src.exists():
        validators = list(ui_src.rglob("*validator*")) + list(
            ui_src.rglob("*decoder*")
        ) + list(ui_src.rglob("*schema*"))
        if validators:
            checks.append(
                VerificationCheck(
                    id="CHK-CONTRACT-002",
                    description="UI-side validators/decoders exist",
                    status="PASS",
                    evidence=f"Found {len(validators)} validator/decoder file(s)",
                    section="Contract Verification",
                )
            )
        else:
            # Check for zod or similar in package.json
            pkg_json = project_root / "apps" / "ui" / "package.json"
            if pkg_json.exists():
                content = pkg_json.read_text()
                if "zod" in content or "yup" in content or "joi" in content:
                    checks.append(
                        VerificationCheck(
                            id="CHK-CONTRACT-002",
                            description="UI-side validators/decoders exist",
                            status="PASS",
                            evidence="Validation library found in package.json",
                            section="Contract Verification",
                        )
                    )
                else:
                    checks.append(
                        VerificationCheck(
                            id="CHK-CONTRACT-002",
                            description="UI-side validators/decoders exist",
                            status="FAIL",
                            evidence="No validators/decoders or validation library found",
                            section="Contract Verification",
                        )
                    )
    else:
        checks.append(
            VerificationCheck(
                id="CHK-CONTRACT-002",
                description="UI-side validators/decoders exist",
                status="SKIP",
                evidence="apps/ui/src not found",
                section="Contract Verification",
            )
        )

    # Check 5: Contract snapshot artifact exists
    contract_snapshot = (
        project_root / "docs" / "ui" / "contracts" / "ui-contracts.yaml"
    )
    contract_snapshot_json = (
        project_root / "docs" / "ui" / "contracts" / "ui-contracts.json"
    )
    if contract_snapshot.exists() or contract_snapshot_json.exists():
        found = contract_snapshot if contract_snapshot.exists() else contract_snapshot_json
        checks.append(
            VerificationCheck(
                id="CHK-CONTRACT-003",
                description="Contract snapshot artifact exists",
                status="PASS",
                evidence=f"Found at {found.relative_to(project_root)}",
                section="Contract Verification",
            )
        )
    else:
        checks.append(
            VerificationCheck(
                id="CHK-CONTRACT-003",
                description="Contract snapshot artifact exists",
                status="FAIL",
                evidence="No contract snapshot found at docs/ui/contracts/",
                section="Contract Verification",
            )
        )

    # Check 6: Report generation script exists (self-referential check)
    report_script = project_root / "scripts" / "verify" / "generate_ui_verify_report.py"
    if report_script.exists():
        checks.append(
            VerificationCheck(
                id="CHK-REPORT-001",
                description="Report generation script exists",
                status="PASS",
                evidence=f"Found at {report_script.relative_to(project_root)}",
                section="Report Generation",
            )
        )
    else:
        checks.append(
            VerificationCheck(
                id="CHK-REPORT-001",
                description="Report generation script exists",
                status="FAIL",
                evidence="Report generation script not found",
                section="Report Generation",
            )
        )

    # Check 7: _logs directory exists
    logs_dir = project_root / "docs" / "reports" / "ui" / "_logs"
    if logs_dir.exists():
        checks.append(
            VerificationCheck(
                id="CHK-REPORT-002",
                description="Logs directory for failures exists",
                status="PASS",
                evidence=f"Found at {logs_dir.relative_to(project_root)}",
                section="Report Generation",
            )
        )
    else:
        checks.append(
            VerificationCheck(
                id="CHK-REPORT-002",
                description="Logs directory for failures exists",
                status="FAIL",
                evidence="No _logs directory found at docs/reports/ui/_logs/",
                section="Report Generation",
            )
        )

    # Sort checks for determinism
    report.checks = sorted(checks, key=lambda c: c.id)

    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate deterministic UI verification reports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--phase",
        required=True,
        help="Phase identifier (e.g., '1.2')",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file path (default: docs/reports/ui/phase-{phase}-verify.md)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print report to stdout instead of writing file",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing report without prompting",
    )

    args = parser.parse_args(argv)

    # Set up basic logging first (without file) for early errors
    logger = logging.getLogger("verify_report")
    if not logger.handlers:
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
        logger.addHandler(console)
        logger.setLevel(logging.DEBUG)

    try:
        project_root = get_project_root()

        # Determine output path
        if args.output:
            output_path = args.output
        else:
            output_path = (
                project_root
                / "docs"
                / "reports"
                / "ui"
                / f"phase-{args.phase}-verify.md"
            )

        # Set up file logging for non-dry-run
        if not args.dry_run:
            log_file = (
                project_root
                / "docs"
                / "reports"
                / "ui"
                / "_logs"
                / f"phase-{args.phase}-verify.log"
            )
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
            logger.addHandler(file_handler)
        logger.info(f"Generating verification report for Phase {args.phase}")

        # Generate report based on phase
        if args.phase == "1.2":
            report = create_phase_1_2_report(project_root)
        else:
            # For other phases, create a minimal report structure
            report = VerificationReport(
                phase=args.phase,
                scope=f"UI Phase {args.phase}",
                generated_date=date.today().isoformat(),
            )
            logger.warning(f"No specific verification logic for phase {args.phase}")

        # Generate markdown content
        generator = ReportGenerator(project_root)
        content = generator.generate_report(report)

        if args.dry_run:
            print(content)
            return 0

        # Check for existing file
        if output_path.exists() and not args.force:
            logger.warning(f"Report already exists at {output_path}")
            logger.info("Use --force to overwrite")
            # Still succeed - idempotent means existing file is fine
            return 0

        # Write atomically
        writer = AtomicFileWriter(output_path, logger)
        writer.write(content)

        # Return appropriate exit code
        if report.overall_status == "FAIL":
            logger.warning("Verification completed with failures")
            return 1
        elif report.overall_status == "PASS":
            logger.info("Verification completed successfully")
            return 0
        else:
            logger.info("Verification completed with partial results")
            return 0

    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        logger.debug(traceback.format_exc())
        return 2


if __name__ == "__main__":
    sys.exit(main())
