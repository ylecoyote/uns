"""Authentication placeholder for UNS Console.

This module provides a minimal authentication integration placeholder
for the read-only UI. In v1, the UI has a read-only posture with no
privileged actions, so authentication is minimal.

Note: This is a placeholder. Actual authentication implementation
will depend on the deployment environment (e.g., OAuth, SSO, API keys).

Security Model:
    - Read-only: No write operations are available
    - No privileged actions: UI cannot modify notifications, policies, or system state
    - Backend is authoritative: All business rules enforced by UNS backend
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class AuthStatus(str, Enum):
    """Authentication status for a user session."""

    AUTHENTICATED = "authenticated"
    ANONYMOUS = "anonymous"
    EXPIRED = "expired"


@dataclass(frozen=True)
class UserContext:
    """Represents the current user context.

    In v1 (read-only), this is a minimal representation.
    The UI does not perform authorization decisions - all
    access control is enforced by the UNS backend.

    Attributes:
        user_id: Unique identifier for the user (or 'anonymous').
        status: Current authentication status.
        display_name: Human-readable display name.
    """

    user_id: str
    status: AuthStatus
    display_name: str = "Anonymous User"

    @property
    def is_authenticated(self) -> bool:
        """Check if the user is authenticated."""
        return self.status == AuthStatus.AUTHENTICATED


class AuthProvider(Protocol):
    """Protocol for authentication providers.

    This protocol defines the interface that authentication
    implementations must satisfy. Implementations may include:
    - NoOpAuthProvider (default, for local development)
    - OAuth2AuthProvider (for production SSO)
    - APIKeyAuthProvider (for service accounts)
    """

    def get_current_user(self) -> UserContext:
        """Get the current user context."""
        ...

    def is_authenticated(self) -> bool:
        """Check if there is an authenticated user."""
        ...


class NoOpAuthProvider:
    """No-operation authentication provider for local development.

    This provider always returns an anonymous user context.
    It is suitable for local development and demo environments
    where authentication is not required.

    Important: This provider should NOT be used in production
    without additional access controls at the infrastructure level.
    """

    def get_current_user(self) -> UserContext:
        """Return an anonymous user context."""
        return UserContext(
            user_id="anonymous",
            status=AuthStatus.ANONYMOUS,
            display_name="Local User (Read-Only)",
        )

    def is_authenticated(self) -> bool:
        """Always returns False for anonymous access."""
        return False


# Global auth provider instance (can be replaced for different environments)
_auth_provider: AuthProvider | None = None


def get_auth_provider() -> AuthProvider:
    """Get the current authentication provider.

    Returns the configured auth provider, or creates a default
    NoOpAuthProvider if none is configured.

    Returns:
        The configured AuthProvider instance.
    """
    global _auth_provider
    if _auth_provider is None:
        _auth_provider = NoOpAuthProvider()
    return _auth_provider


def configure_auth_provider(provider: AuthProvider) -> None:
    """Configure the authentication provider.

    Args:
        provider: The AuthProvider implementation to use.
    """
    global _auth_provider
    _auth_provider = provider


def reset_auth_provider() -> None:
    """Reset the authentication provider to default.

    This is primarily useful for testing.
    """
    global _auth_provider
    _auth_provider = None


def get_current_user() -> UserContext:
    """Get the current user context.

    Convenience function that gets the auth provider and
    returns the current user.

    Returns:
        The current UserContext.
    """
    return get_auth_provider().get_current_user()
