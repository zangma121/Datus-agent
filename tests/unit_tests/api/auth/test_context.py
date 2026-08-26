"""Spec for AppContext tenant identity (datus-agent-cube M1a).

``tenant_id`` is the first-class tenant boundary: ``None`` keeps the
single-tenant (default-tenant) behavior unchanged.
"""

from datus.api.auth.context import AppContext


class TestAppContextTenantId:
    def test_tenant_id_defaults_to_none_for_single_tenant_compat(self):
        ctx = AppContext()
        assert ctx.tenant_id is None

    def test_tenant_id_is_settable_alongside_user_and_project(self):
        ctx = AppContext(tenant_id="org-42", user_id="alice", project_id="demo")
        assert ctx.tenant_id == "org-42"
        assert ctx.user_id == "alice"
        assert ctx.project_id == "demo"
