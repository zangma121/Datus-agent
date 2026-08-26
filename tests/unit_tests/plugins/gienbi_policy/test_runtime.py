"""Spec for the gienbi-policy plugin (datus-agent-cube M4, T4.1–T4.3).

GienBI's MySQL permission model, applied at Datus' policy seams:

- metric-level: ``user_resource_permission_flat`` VIEW bit gates which
  metrics a user may even see (``before_metric_read``)
- org owners bypass every check
- ``validate_context`` fails closed in multi-tenant deployments when the
  GienBI identity (org/user) is missing

Tests run against a SQLite fixture shaped like the GienBI tables; the
MySQL ``%s`` paramstyle is adapted on the test side so the production
reader stays MySQL-shaped.
"""

import sqlite3
import time
from unittest.mock import MagicMock

import pytest

from datus.utils.exceptions import DatusException


class SqliteGienbiFixture:
    """In-memory GienBI permission tables with the production query shapes."""

    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE user_resource_permission_flat (
                org_id TEXT, user_id TEXT, resource_type TEXT,
                resource_id TEXT, permission INTEGER
            );
            CREATE TABLE role (id TEXT PRIMARY KEY, org_id TEXT, type TEXT);
            CREATE TABLE user_role (org_id TEXT, user_id TEXT, role_id TEXT);
            """
        )

    def execute(self, sql, params):
        # Adapt MySQL %s paramstyle to sqlite's ?
        return [dict(r) for r in self.conn.execute(sql.replace("%s", "?"), params).fetchall()]

    def add_metric_permission(self, org, user, metric_id, permission):
        self.conn.execute(
            "INSERT INTO user_resource_permission_flat VALUES (?,?,?,?,?)",
            (org, user, "METRIC", metric_id, permission),
        )

    def add_owner(self, org, user):
        self.conn.execute("INSERT INTO role VALUES ('r1', ?, 'ORG_OWNER')", (org,))
        self.conn.execute("INSERT INTO user_role VALUES (?, ?, 'r1')", (org, user))


@pytest.fixture
def gienbi_db():
    return SqliteGienbiFixture()


def _runtime(gienbi_db, multi_tenant=True):
    from datus_gienbi_policy.runtime import create_runtime

    return create_runtime(
        {
            "multi_tenant": multi_tenant,
            "connection_factory": lambda: gienbi_db,
        }
    )


class TestPluginSkeleton:
    def test_factory_returns_hooked_runtime(self, gienbi_db):
        runtime = _runtime(gienbi_db)
        for hook in ("validate_context", "before_sql_read", "before_metric_read", "after_read_result"):
            assert callable(getattr(runtime, hook, None)), hook


class TestValidateContext:
    def test_multi_tenant_requires_identity(self, gienbi_db):
        runtime = _runtime(gienbi_db, multi_tenant=True)
        result = runtime.validate_context({})
        assert result["allowed"] is False

    def test_multi_tenant_with_identity_passes(self, gienbi_db):
        runtime = _runtime(gienbi_db, multi_tenant=True)
        result = runtime.validate_context({"gienbi_org_id": "org-1", "gienbi_user_id": "alice"})
        assert result["allowed"] is True

    def test_single_tenant_passes_without_identity(self, gienbi_db):
        runtime = _runtime(gienbi_db, multi_tenant=False)
        assert runtime.validate_context({})["allowed"] is True


class TestBeforeMetricRead:
    def _ctx(self, org="org-1", user="alice"):
        return {"gienbi_org_id": org, "gienbi_user_id": user}

    def test_view_bit_gates_metrics(self, gienbi_db):
        gienbi_db.add_metric_permission("org-1", "alice", "m_allowed", 2)  # VIEW only
        gienbi_db.add_metric_permission("org-1", "alice", "m_denied", 1)  # no VIEW bit
        runtime = _runtime(gienbi_db)

        decision = runtime.before_metric_read(
            ["m_allowed", "m_denied", "m_unknown"], datasource="bank", policy_context=self._ctx()
        )
        assert decision["allowed"] is True
        assert decision["allowed_metrics"] == ["m_allowed"]
        denied = {d["metric"]: d for d in decision["denied"]}
        assert set(denied) == {"m_denied", "m_unknown"}

    def test_org_owner_bypasses(self, gienbi_db):
        gienbi_db.add_owner("org-1", "boss")
        runtime = _runtime(gienbi_db)
        decision = runtime.before_metric_read(
            ["m1", "m2"], datasource="bank", policy_context=self._ctx(user="boss")
        )
        assert decision["allowed_metrics"] == ["m1", "m2"]
        assert decision["denied"] == []

    def test_missing_identity_in_multi_tenant_fails_closed(self, gienbi_db):
        runtime = _runtime(gienbi_db, multi_tenant=True)
        decision = runtime.before_metric_read(["m1"], datasource="bank", policy_context={})
        assert decision["allowed"] is False


class TestPermissionCache:
    def test_results_cached_within_ttl(self, gienbi_db):
        from datus_gienbi_policy.permissions import PermissionReader

        reader = PermissionReader(connection_factory=lambda: gienbi_db, ttl_seconds=60)
        gienbi_db.add_metric_permission("org-1", "alice", "m1", 2)

        assert reader.view_permission("org-1", "alice", "METRIC", "m1") is True
        # Change the table; cached result must still be served within TTL.
        gienbi_db.conn.execute("DELETE FROM user_resource_permission_flat")
        assert reader.view_permission("org-1", "alice", "METRIC", "m1") is True

    def test_cache_expires_after_ttl(self, gienbi_db):
        from datus_gienbi_policy.permissions import PermissionReader

        reader = PermissionReader(connection_factory=lambda: gienbi_db, ttl_seconds=0.05)
        gienbi_db.add_metric_permission("org-1", "alice", "m1", 2)
        assert reader.view_permission("org-1", "alice", "METRIC", "m1") is True
        time.sleep(0.1)
        gienbi_db.conn.execute("DELETE FROM user_resource_permission_flat")
        assert reader.view_permission("org-1", "alice", "METRIC", "m1") is False
