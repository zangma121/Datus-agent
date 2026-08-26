# Copyright 2025-present DatusAI, Inc.
# Licensed under the Apache License, Version 2.0.
# See http://www.apache.org/licenses/LICENSE-2.0 for details.

"""Row-level datasource scoping helpers for project-scoped storage.

Physical storage namespaces remain project-scoped. Datasource isolation is
represented by columns inside each shared project table, and tenant
isolation (tenant > project, datus-agent-cube M1b) by a ``storage_key``
prefix: the default tenant keeps the legacy ``{datasource}:{row_id}`` key
and no extra filter, while a non-default tenant reads and writes
``{tenant}:{datasource}:{row_id}`` rows with a ``storage_key LIKE`` scope.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional

from datus_storage_base.conditions import Node, and_, eq, like

from datus.utils.exceptions import DatusException, ErrorCode

if TYPE_CHECKING:
    from datus.configuration.agent_config import AgentConfig

DATASOURCE_ID_COLUMN = "datasource_id"
STORAGE_KEY_COLUMN = "storage_key"
TENANT_ID_COLUMN = "tenant_id"
LEGACY_DATASOURCE_ID = ""
LEGACY_STORAGE_KEY_PREFIX = "legacy:"

#: Reserved tenant for single-tenant deployments; keeps the legacy key format.
DEFAULT_TENANT_ID = "default"

# Tenant ids end up inside storage keys, so restrict to path-safe characters
# (the auth provider already enforces the same alphabet; this is defense in
# depth for programmatic callers).
_TENANT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def validate_tenant_id(tenant_id: Optional[str]) -> Optional[str]:
    resolved = str(tenant_id or "").strip()
    if not resolved or resolved == DEFAULT_TENANT_ID:
        return None
    if not _TENANT_ID_PATTERN.match(resolved):
        raise DatusException(
            ErrorCode.STORAGE_INVALID_ARGUMENT,
            message_args={
                "error_message": (
                    f"invalid tenant_id {resolved!r}: only letters, digits, underscore and hyphen are allowed"
                )
            },
        )
    return resolved


def resolve_tenant_id(
    agent_config: "AgentConfig",
    tenant_id: Optional[str] = None,
) -> Optional[str]:
    """Return the normalized tenant id for scoped storage (``None`` = default).

    Precedence: explicit argument -> ``agent_config.tenant_id`` (set on
    per-tenant config clones by the service cache) -> ``default``.
    """
    if isinstance(tenant_id, str) and tenant_id.strip():
        return validate_tenant_id(tenant_id)
    configured = getattr(agent_config, "tenant_id", None)
    if isinstance(configured, str) and configured.strip():
        return validate_tenant_id(configured)
    return None


def resolve_datasource_id(agent_config: "AgentConfig", datasource_id: Optional[str] = None) -> str:
    """Return the datasource id required by datasource-scoped KB stores."""

    raw_value = datasource_id if datasource_id is not None else getattr(agent_config, "current_datasource", "")
    resolved = str(raw_value or "").strip()
    if not resolved:
        raise DatusException(
            ErrorCode.STORAGE_INVALID_ARGUMENT,
            message_args={"error_message": "datasource is required for datasource-scoped storage"},
        )
    return resolved


def datasource_condition(datasource_id: str, tenant_id: Optional[str] = None, *, tenant_column: bool = False) -> Node:
    """Build a WHERE condition for the datasource row scope.

    With a non-default ``tenant_id`` the condition additionally narrows to
    that tenant: either by the ``tenant_id`` column (``tenant_column=True``,
    for stores whose schema carries the column) or by a ``storage_key``
    prefix match (column-free fallback, so tenant rows are invisible to
    other tenants without a schema migration).
    """

    condition: Node = eq(DATASOURCE_ID_COLUMN, datasource_id)
    tenant = validate_tenant_id(tenant_id)
    if tenant_column:
        # Default-tenant rows and legacy rows carry '' in tenant_id, so the
        # equality also excludes foreign-tenant rows from default reads.
        return and_(condition, eq(TENANT_ID_COLUMN, tenant or ""))
    if tenant is not None:
        condition = and_(condition, tenant_condition(tenant))
    return condition


def tenant_condition(tenant_id: Optional[str]) -> Optional[Node]:
    """Build the tenant scope condition, or ``None`` for the default tenant."""

    tenant = validate_tenant_id(tenant_id)
    if tenant is None:
        return None
    # ``*`` is the conditions library's wildcard (converted to SQL ``%``);
    # a literal ``%`` in the pattern would be escaped instead.
    return like(STORAGE_KEY_COLUMN, f"{tenant}:*")


def combine_conditions(conditions: Iterable[Optional[Node]]) -> Optional[Node]:
    """Combine non-empty conditions with AND."""

    active = [condition for condition in conditions if condition is not None]
    if not active:
        return None
    if len(active) == 1:
        return active[0]
    return and_(*active)


def build_storage_key(datasource_id: str, business_id: Any, tenant_id: Optional[str] = None) -> str:
    """Build an internal datasource-scoped unique key for vector upserts.

    Default tenant keeps the legacy ``{datasource}:{row_id}`` format so
    existing rows stay addressable; other tenants get
    ``{tenant}:{datasource}:{row_id}``.
    """

    row_id = str(business_id or "").strip()
    if not row_id:
        raise DatusException(
            ErrorCode.STORAGE_INVALID_ARGUMENT,
            message_args={"error_message": "business id is required to build storage_key"},
        )
    tenant = validate_tenant_id(tenant_id)
    datasource = str(datasource_id or "").strip()
    if tenant is not None:
        return f"{tenant}:{datasource}:{row_id}"
    if datasource:
        return f"{datasource}:{row_id}"
    return f"{LEGACY_STORAGE_KEY_PREFIX}{row_id}"


def add_datasource_scope_to_rows(
    rows: List[Dict[str, Any]],
    datasource_id: str,
    *,
    id_field: str = "id",
    tenant_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return copies of rows with datasource_id and storage_key populated."""

    scoped_rows: List[Dict[str, Any]] = []
    for row in rows:
        scoped = dict(row)
        scoped[DATASOURCE_ID_COLUMN] = datasource_id
        if id_field and scoped.get(id_field) not in (None, ""):
            scoped[STORAGE_KEY_COLUMN] = build_storage_key(datasource_id, scoped[id_field], tenant_id=tenant_id)
        scoped_rows.append(scoped)
    return scoped_rows
