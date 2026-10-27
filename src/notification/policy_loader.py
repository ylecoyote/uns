"""YAML policy loading for standalone UNS Core extraction."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from notification.policies import (
    NotificationPolicy,
    PolicyRegistry,
    PolicyStatus,
    get_policy_registry,
)

_HASH_EXCLUDED_FIELDS = {"description", "config_id", "config_hash"}


def load_policy_from_yaml(
    path: str | Path,
    registry: PolicyRegistry | None = None,
) -> NotificationPolicy:
    """Load one notification policy YAML file and optionally register it."""
    policy_path = Path(path)
    if not policy_path.exists():
        raise FileNotFoundError(str(policy_path))

    try:
        data = yaml.safe_load(policy_path.read_text())
    except yaml.YAMLError as exc:
        raise ValueError("Invalid policy YAML") from exc
    if data is None:
        raise ValueError(f"Empty or null policy YAML: {policy_path}")
    if not isinstance(data, dict):
        raise ValueError(f"Policy YAML must contain an object: {policy_path}")
    if "notification_type" not in data:
        raise ValueError(f"Policy YAML missing notification_type: {policy_path}")

    parsed = NotificationPolicy.from_dict(data)
    policy = parsed.model_copy(
        update={
            "config_hash": compute_policy_content_hash(
                parsed.model_dump(mode="json", exclude={"config_id", "config_hash"})
            )
        }
    )
    if registry is not None:
        registry.register(policy)
    return policy


def load_policies_from_directory(
    path: str | Path,
    registry: PolicyRegistry | None = None,
) -> int:
    """Load all `.yaml` and `.yml` policies in a directory."""
    policy_dir = Path(path)
    if not policy_dir.exists():
        raise FileNotFoundError(str(policy_dir))
    if not policy_dir.is_dir():
        raise NotADirectoryError(str(policy_dir))

    target_registry = registry if registry is not None else get_policy_registry()
    count = 0
    for policy_path in sorted([*policy_dir.glob("*.yaml"), *policy_dir.glob("*.yml")]):
        load_policy_from_yaml(policy_path, registry=target_registry)
        count += 1
    return count


def load_runtime_registry_from_directory(path: str | Path) -> tuple[int, PolicyRegistry]:
    """Load YAML policies and return an ACTIVE-only runtime registry."""
    staging_registry = PolicyRegistry(runtime_only=False)
    loaded_count = load_policies_from_directory(path, registry=staging_registry)
    runtime_registry = PolicyRegistry()
    for policy in staging_registry.get_all().values():
        if policy.status == PolicyStatus.ACTIVE:
            runtime_registry.register(policy)
    return loaded_count, runtime_registry


def compute_policy_content_hash(data: dict[str, Any]) -> str:
    """Return a stable SHA-256 hash for policy semantics.

    Human-only metadata such as `description` and persistence identity fields
    (`config_id`, `config_hash`) are excluded so copy edits or hydration do not
    create a different semantic policy hash.
    """
    if "notification_type" in data and "policies" not in data:
        try:
            if (
                isinstance(data.get("channels"), dict)
                or isinstance(data.get("require_ack"), dict)
                or "delivery_mode_by_autonomy" in data
            ):
                normalized = NotificationPolicy.from_dict(data)
            else:
                normalized = NotificationPolicy.model_validate(data)
            semantic_data = normalized.model_dump(
                mode="json", exclude={"config_id", "config_hash"}
            )
        except Exception:
            semantic_data = {
                key: value for key, value in data.items() if key not in _HASH_EXCLUDED_FIELDS
            }
    else:
        semantic_data = {
            key: value for key, value in data.items() if key not in _HASH_EXCLUDED_FIELDS
        }
    payload = json.dumps(semantic_data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
