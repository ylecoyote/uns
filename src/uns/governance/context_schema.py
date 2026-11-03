"""ContextSchema registration, load-time policy field validation, and capsule validation.

Implements the ContextSchema contract (ADR Context Schema Registration):
- Domain callers declare a ``ContextSchema`` as a Pydantic v2 ``BaseModel`` subclass.
- At policy-load time, ``validate_policy_against_schema`` resolves every ``when``
  condition's ``field`` path against the registered schema and checks operator/type
  compatibility before a policy can become active.
- At evaluate-time, ``validate_context_capsule`` validates the input capsule against
  the registered schema, raising ``MissingFieldError`` or ``ContextSchemaViolation``.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel, ValidationError

from uns.governance.errors import (
    ContextSchemaViolation,
    MissingFieldError,
    PolicyLoadError,
)
from uns.governance.operators import Operator
from uns.governance.policy_dsl import Policy

ContextSchema = type[BaseModel]

_SEGMENT_PATTERN = re.compile(
    r"""
    (?:"([^"]+)")          # Quoted segment: "external.id"
    |([A-Za-z_][A-Za-z0-9_]*) # Identifier segment
    |(?:\[(\d+)\])         # List index: [0]
    """,
    re.VERBOSE,
)


def parse_field_path(field_path: str) -> list[str | int]:
    """Parse a dot/bracket field path into path segments.

    Examples:
        ``"notional_usd"`` -> ``["notional_usd"]``
        ``"instrument.symbol"`` -> ``["instrument", "symbol"]``
        ``"approvers[0].role"`` -> ``["approvers", 0, "role"]``
        ``'metadata."external.id"'`` -> ``["metadata", "external.id"]``
    """
    if not field_path or not field_path.strip():
        raise PolicyLoadError("Field path must not be empty")

    segments: list[str | int] = []
    pos = 0
    raw = field_path.strip()
    n = len(raw)

    while pos < n:
        if raw[pos] == ".":
            if not segments:
                raise PolicyLoadError(f"Invalid leading dot in field path {field_path!r}")
            pos += 1
            if pos >= n:
                raise PolicyLoadError(f"Invalid trailing dot in field path {field_path!r}")
        match = _SEGMENT_PATTERN.match(raw, pos)
        if not match:
            raise PolicyLoadError(f"Malformed field path {field_path!r} at position {pos}")
        quoted, ident, index_str = match.groups()
        if quoted is not None:
            segments.append(quoted)
        elif ident is not None:
            segments.append(ident)
        elif index_str is not None:
            segments.append(int(index_str))
        pos = match.end()

    return segments


def _unwrap_optional(annotation: Any) -> Any:
    """Unwrap Optional[T] / T | None to T."""
    origin = get_origin(annotation)
    if origin is Union or str(origin) == "typing.Union" or type(annotation).__name__ == "UnionType":
        non_none = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return annotation


def _resolve_schema_field_type(
    schema_cls: type[BaseModel],
    field_path: str,
    *,
    schema_name: str,
) -> Any:
    """Walk a Pydantic BaseModel class hierarchy to resolve the leaf type annotation."""
    segments = parse_field_path(field_path)
    current_type: Any = schema_cls

    for seg in segments:
        current_type = _unwrap_optional(current_type)
        if isinstance(seg, int):
            origin = get_origin(current_type)
            args = get_args(current_type)
            if origin in (list, tuple) and args:
                current_type = _unwrap_optional(args[0])
                continue
            raise ContextSchemaViolation(
                f"Field path {field_path!r} indexes into non-list type in schema {schema_name!r}",
                field_path=field_path,
                schema_name=schema_name,
            )

        if isinstance(current_type, type) and issubclass(current_type, BaseModel):
            model_fields = current_type.model_fields
            if seg not in model_fields:
                raise ContextSchemaViolation(
                    f"Field {field_path!r} (segment {seg!r}) is not registered in ContextSchema {schema_name!r}",
                    field_path=field_path,
                    schema_name=schema_name,
                )
            current_type = model_fields[seg].annotation
            continue

        origin = get_origin(current_type)
        args = get_args(current_type)
        if origin in (dict, Mapping):
            current_type = args[1] if len(args) >= 2 else Any
            continue

        if current_type is Any:
            return Any

        raise ContextSchemaViolation(
            f"Field {field_path!r} traverses non-object field at {seg!r} in ContextSchema {schema_name!r}",
            field_path=field_path,
            schema_name=schema_name,
        )

    return _unwrap_optional(current_type)


def _check_operator_type_compatibility(
    operator: Operator,
    leaf_type: Any,
    field_path: str,
) -> None:
    """Validate at policy-load time that the operator is compatible with the schema field type."""
    if leaf_type is Any or leaf_type is None:
        return

    origin = get_origin(leaf_type)
    if operator in (Operator.GT, Operator.GTE, Operator.LT, Operator.LTE):
        if leaf_type is bool or (
            isinstance(leaf_type, type)
            and not issubclass(leaf_type, (int, float))
        ):
            raise PolicyLoadError(
                f"Operator {operator.value} on field {field_path!r} requires int/float schema type, "
                f"got {getattr(leaf_type, '__name__', str(leaf_type))}"
            )
    elif operator == Operator.MATCHES and (
        origin is not None or (isinstance(leaf_type, type) and not issubclass(leaf_type, str))
    ):
        raise PolicyLoadError(
            f"Operator MATCHES on field {field_path!r} requires str schema type, "
            f"got {getattr(leaf_type, '__name__', str(leaf_type))}"
        )


def validate_policy_against_schema(
    policy: Policy,
    schema_cls: type[BaseModel],
    *,
    schema_name: str | None = None,
) -> None:
    """Validate all field references and operator types in a Policy against a ContextSchema."""
    resolved_name = schema_name or policy.context_schema
    for rule in policy.rules:
        for cond in rule.when:
            leaf_type = _resolve_schema_field_type(
                schema_cls,
                cond.field,
                schema_name=resolved_name,
            )
            _check_operator_type_compatibility(cond.operator, leaf_type, cond.field)


def validate_context_capsule(
    context: BaseModel | Mapping[str, Any],
    schema_cls: type[BaseModel],
    *,
    schema_name: str | None = None,
) -> BaseModel:
    """Validate an evaluation-time context capsule against its registered ContextSchema."""
    if isinstance(context, schema_cls):
        return context

    raw_data = context.model_dump() if isinstance(context, BaseModel) else context
    if not isinstance(raw_data, Mapping):
        raise ContextSchemaViolation(
            f"Context capsule must be a mapping or {schema_cls.__name__}, got {type(context).__name__}",
            schema_name=schema_name or schema_cls.__name__,
        )

    try:
        return schema_cls.model_validate(raw_data)
    except ValidationError as exc:
        resolved_name = schema_name or schema_cls.__name__
        for err in exc.errors():
            loc = ".".join(str(part) for part in err.get("loc", ()))
            if err.get("type") == "missing":
                raise MissingFieldError(
                    field_path=loc or "<root>",
                    schema_name=resolved_name,
                ) from exc
        first_loc = (
            ".".join(str(part) for part in exc.errors()[0].get("loc", ()))
            if exc.errors()
            else None
        )
        raise ContextSchemaViolation(
            f"Context capsule failed validation for schema {resolved_name!r}: {exc}",
            field_path=first_loc,
            schema_name=resolved_name,
        ) from exc


def resolve_field_path(
    context: BaseModel | Mapping[str, Any],
    field_path: str,
) -> tuple[bool, Any]:
    """Resolve a dot/bracket field path against a validated model or dict.

    Returns ``(exists, value)`` where ``exists`` is False when a key/index is
    absent or its value is ``None``.
    """
    segments = parse_field_path(field_path)
    cursor: Any = context

    for seg in segments:
        if cursor is None:
            return False, None
        if isinstance(seg, int):
            if isinstance(cursor, (list, tuple)) and 0 <= seg < len(cursor):
                cursor = cursor[seg]
            else:
                return False, None
        elif isinstance(cursor, BaseModel):
            if hasattr(cursor, seg):
                cursor = getattr(cursor, seg)
            else:
                return False, None
        elif isinstance(cursor, Mapping):
            if seg in cursor:
                cursor = cursor[seg]
            else:
                return False, None
        else:
            return False, None

    return (cursor is not None), cursor


def compute_context_hash(context: BaseModel | Mapping[str, Any]) -> str:
    """Compute a deterministic SHA-256 hash of a context capsule without storing raw PII."""
    payload = context.model_dump(mode="json") if isinstance(context, BaseModel) else dict(context)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
