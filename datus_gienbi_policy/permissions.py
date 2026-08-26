# Copyright 2025-present DatusAI, Inc.
# Licensed under the Apache License, Version 2.0.
# See http://www.apache.org/licenses/LICENSE-2.0 for details.

"""GienBI permission reading with a per-user TTL cache.

Reads the shared GienBI MySQL tables directly (same source of truth as
chat2agent's ``resource_permission.py``): metric-level VIEW bits from
``user_resource_permission_flat``, org-owner bypass via ``role``/
``user_role``. Queries use the MySQL ``%s`` paramstyle; test fixtures
adapt on their side.
"""

import time
from typing import Any, Callable, Dict, Tuple

from datus.utils.loggings import get_logger

logger = get_logger(__name__)

#: chat2agent ``resource_permission.py``: bit 2 is VIEW.
VIEW_PERMISSION_BIT = 2


class PermissionReader:
    """Cached reads over the GienBI permission tables.

    ``connection_factory`` returns a DB-API connection with ``execute(sql,
    params) -> list[dict]`` semantics (rows as dicts). Caching is per
    ``(org, user)`` with a TTL so permission changes surface within
    ``ttl_seconds`` without hammering MySQL on every metric read.
    """

    def __init__(self, connection_factory: Callable[[], Any], ttl_seconds: float = 60.0):
        self._connection_factory = connection_factory
        self._ttl_seconds = ttl_seconds
        self._cache: Dict[Tuple[str, str], Tuple[float, "_UserPermissions"]] = {}

    # ── public API ───────────────────────────────────────────────────

    def view_permission(self, org_id: str, user_id: str, resource_type: str, resource_id: str) -> bool:
        perms = self._user_permissions(org_id, user_id)
        permission = perms.metrics.get((resource_type, resource_id))
        return permission is not None and (permission & VIEW_PERMISSION_BIT) != 0

    def is_org_owner(self, org_id: str, user_id: str) -> bool:
        return self._user_permissions(org_id, user_id).org_owner

    # ── caching ──────────────────────────────────────────────────────

    def _user_permissions(self, org_id: str, user_id: str) -> "_UserPermissions":
        key = (org_id, user_id)
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached is not None and now - cached[0] < self._ttl_seconds:
            return cached[1]

        permissions = self._load(org_id, user_id)
        self._cache[key] = (now, permissions)
        return permissions

    def _load(self, org_id: str, user_id: str) -> "_UserPermissions":
        conn = self._connection_factory()
        try:
            rows = conn.execute(
                """
                SELECT resource_type, resource_id, permission
                FROM user_resource_permission_flat
                WHERE org_id = %s AND user_id = %s
                """,
                (org_id, user_id),
            )
            metrics: Dict[Tuple[str, str], int] = {}
            for row in rows or []:
                try:
                    metrics[(str(row.get("resource_type") or ""), str(row.get("resource_id") or ""))] = int(
                        row.get("permission") or 0
                    )
                except (TypeError, ValueError):
                    continue

            owner_rows = conn.execute(
                """
                SELECT 1 AS is_owner
                FROM user_role ur
                JOIN role r ON r.id = ur.role_id
                WHERE ur.org_id = %s AND ur.user_id = %s AND r.type = 'ORG_OWNER'
                LIMIT 1
                """,
                (org_id, user_id),
            )
            org_owner = bool(owner_rows)
            return _UserPermissions(metrics=metrics, org_owner=org_owner)
        except Exception as exc:  # noqa: BLE001 - surface as denied, never crash reads
            logger.error("GienBI permission read failed (denying): %s", exc)
            return _UserPermissions(metrics={}, org_owner=False)


class _UserPermissions:
    __slots__ = ("metrics", "org_owner")

    def __init__(self, metrics: Dict[Tuple[str, str], int], org_owner: bool):
        self.metrics = metrics
        self.org_owner = org_owner
