# Contributing to UNS

Thank you for your interest in contributing to the Unified Notification Service (UNS).

## Development Setup

### Prerequisites

**Backend:**
- Python 3.10 or higher
- pip or uv package manager
- Redis (for integration tests)

**UI (apps/ui):**
- Node.js 20 or higher
- npm (included with Node.js)

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd unified-notification-service

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install with development dependencies
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/notification/test_sdk.py

# Run tests matching pattern
pytest -k "test_safety"

# Run with verbose output
pytest -v
```

### Code Quality

```bash
# Lint code
ruff check src tests

# Auto-fix lint issues
ruff check --fix src tests

# Format code
ruff format src tests

# Type check
mypy src
```

### UI Development (apps/ui)

The UI is a React/TypeScript application built with Vite. All UI code is in `apps/ui/`.

```bash
# Navigate to UI directory
cd apps/ui

# Install dependencies
npm ci

# Start development server (proxies to backend on port 8000)
npm run dev

# Run linting
npm run lint

# Run type checking
npm run type-check

# Run tests (interactive)
npm run test

# Run tests once (for CI)
npm run test:run

# Run tests with coverage
npm run test:coverage

# Build for production
npm run build

# Run full CI pipeline locally
npm run ci
```

**UI CI Requirements:**
- ESLint must pass with zero warnings (`--max-warnings 0`)
- TypeScript must have no type errors
- All tests must pass (minimum 50% coverage threshold)
- Production build must succeed

## Project Structure

```
src/
├── notification/           # Core notification package
│   ├── models.py          # Data contracts
│   ├── interfaces.py      # Integration protocols
│   ├── policies.py        # Policy schema & registry
│   ├── sdk.py             # Producer interface
│   ├── service.py         # Delivery orchestration
│   ├── deduplication.py   # Deduplication engine
│   ├── rate_limiting.py   # Rate limiting
│   ├── acknowledgment.py  # Ack lifecycle
│   ├── audit.py           # Audit logging
│   └── adapters/          # Channel adapters
├── db/                    # Database models
└── mcp_server/            # HTTP API routes

tests/
└── notification/          # Test files mirror src structure

apps/
└── ui/                    # React UI application
    ├── src/
    │   ├── api/           # Typed API client
    │   ├── components/    # React components
    │   ├── hooks/         # Custom React hooks
    │   ├── pages/         # Page components
    │   ├── types/         # TypeScript types
    │   └── utils/         # Utilities
    └── tests/             # Component and integration tests
```

## Coding Standards

### Style Guide

- Follow PEP 8 with Ruff enforcement
- Maximum line length: 100 characters
- Use type hints for all function signatures
- Use docstrings for public functions and classes

### Naming Conventions

- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private members: `_leading_underscore`

### Documentation

- All public APIs must have docstrings
- Use Google-style docstrings:

```python
def send_safety(
    notification_type: str,
    title: str,
    message: str,
    source: str,
    autonomy_context: AutonomyContext | None = None,
) -> NotificationResult:
    """Send a SAFETY intent notification.

    SAFETY notifications have GUARANTEED delivery and require acknowledgment
    in LIVE mode by default.

    Args:
        notification_type: Namespaced notification type
        title: Notification title
        message: Notification body
        source: Producer identifier
        autonomy_context: Required autonomy context

    Returns:
        NotificationResult with delivery outcome

    Raises:
        ValidationError: If autonomy_context is missing or invalid
    """
```

## Testing Guidelines

### Test Organization

- One test file per source module
- Test classes named `Test<ClassName>`
- Test methods named `test_<behavior>`

### Test Categories

1. **Unit Tests**: Test individual functions/methods in isolation
2. **Integration Tests**: Test component interactions
3. **Contract Tests**: Verify API contracts and invariants

### Writing Good Tests

```python
class TestNotificationSDK:
    """Tests for NotificationSDK."""

    def test_send_safety_with_valid_context_succeeds(self):
        """SAFETY notification with valid context should succeed."""
        sdk = NotificationSDK()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        result = sdk.send_safety(
            notification_type="test.safety",
            title="Test",
            message="Test message",
            source="test",
            autonomy_context=context,
        )

        assert result.status == DeliveryStatus.SUCCESS

    def test_send_without_context_raises_validation_error(self):
        """Sending without autonomy_context should raise ValidationError."""
        sdk = NotificationSDK()

        with pytest.raises(ValidationError) as exc_info:
            sdk.send_safety(
                notification_type="test.safety",
                title="Test",
                message="Test message",
                source="test",
            )

        assert "autonomy_context" in str(exc_info.value)
```

### Test Coverage

- Aim for 90%+ code coverage
- Cover edge cases and error conditions
- Test invariants documented in PRD

## Pull Request Process

### Before Submitting

1. Run all tests and ensure they pass
2. Run linting and fix any issues
3. Run type checking and fix any issues
4. Update documentation if needed
5. Add tests for new functionality

### PR Guidelines

1. **Title**: Clear, concise description of changes
2. **Description**: Explain what and why, not how
3. **Size**: Keep PRs focused and reviewable
4. **Commits**: Logical, atomic commits with clear messages

### Commit Messages

Follow conventional commits:

```
type(scope): description

[optional body]

[optional footer]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Formatting, no code change
- `refactor`: Code change that neither fixes nor adds
- `test`: Adding or correcting tests
- `chore`: Maintenance tasks

Examples:
```
feat(sdk): add send_governance convenience method
fix(dedup): handle Redis connection failures gracefully
docs(readme): add policy configuration examples
test(adapters): add integration tests for Slack adapter
```

## Invariants (Must/Never/Always Statements)

For full definitions and enforcement options, see `docs/verification/invariants.md`.

### When this applies
If your PR introduces, changes, or removes any statement that asserts a strong property using words like:
- must / must not
- never / always
- guaranteed
- required / forbidden
- invariant / cannot happen

…then this section applies.

### Requirements for invariant changes
1. **Update the invariant registry**
   - Add/update an entry in `docs/verification/invariants.yml`
   - Include severity, enforcement type (guard/isolation/test/exception), and evidence links.

2. **Run invariant verification**
   - Run `/verify_invariants <affected paths>` and attach the output to the PR
   - Or provide an equivalent bounded-verification artifact generated via Ralphy tasks.

3. **Provide enforcement evidence**
   - For `guard`: link to the guard code and rationale
   - For `test`: link to the test(s) that fail on violation
   - For `isolation`: document the structural constraint that prevents violations
   - For `exception`: include rationale, owner, and mitigation plan

### Reviewer checklist (invariant PRs)
- Registry updated (`docs/verification/invariants.yml`)
- Verification output attached (`/verify_invariants` or equivalent)
- Enforcement evidence is clear and appropriately scoped
- Any exception is explicitly owned and risk-accepted

## Architecture Decisions

### Key Invariants

1. **INV-CTX-001** — `autonomy_context` is REQUIRED for all notifications
2. **INV-CTX-002** — `autonomy_mode` and `agent_id` must be set in context
3. **INV-DEL-001** — SAFETY and GOVERNANCE use GUARANTEED delivery
4. **INV-ACK-001** — SAFETY in LIVE mode requires acknowledgment
5. **INV-MSG-001** — Title max 200 chars, message max 4000 chars

### Adding New Features

1. Review the PRD and architecture docs
2. Ensure feature aligns with design principles
3. Add tests before implementing
4. Update documentation

### Adding New Channels

1. Create adapter in `src/notification/adapters/`
2. Implement `BaseAdapter` protocol
3. Add to `Channel` enum
4. Register in adapter factory
5. Add rate limit defaults
6. Add tests

## Getting Help

- Check existing documentation in `/docs`
- Review the PRD (`prd.md`) for specifications
- Open an issue for questions

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
