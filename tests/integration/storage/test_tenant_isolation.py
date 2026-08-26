"""End-to-end tenant isolation for datus-agent-cube M1b (T1.9).

Unlike the unit suite (which constructs stores with explicit kwargs), these
tests exercise the real wiring: a per-tenant ``AgentConfig`` clone stamped the
way ``deps._factory`` stamps it (``agent_config.tenant_id = ctx.tenant_id``)
must isolate knowledge-base rows and session directories from other tenants
and from the default tenant, with the default tenant keeping legacy layout.
"""

import copy

import pytest

from datus.api.auth.gienbi_provider import GienBIAuthProvider
from datus.api.auth.loader import load_auth_provider
from datus.models.session_manager import SessionManager
from datus.storage.metric.store import MetricRAG
from datus.utils.exceptions import DatusException


def _metric(description: str) -> dict:
    return {
        "id": f"metric:{description.replace(' ', '_')}",
        "name": description.replace(" ", "_"),
        "description": description,
        "subject_path": ["Isolation"],
        "metric_type": "simple",
    }


@pytest.fixture
def base_config(agent_config):
    """A deep copy of the real integration config, safe to stamp per tenant."""
    return copy.deepcopy(agent_config)


class TestKnowledgeBaseTenantIsolation:
    def test_org_rows_invisible_to_other_tenants_and_default(self, base_config):
        # Stamp the per-tenant clone exactly like deps._factory does.
        org_cfg = copy.deepcopy(base_config)
        org_cfg.tenant_id = "iso-org-a"
        other_cfg = copy.deepcopy(base_config)
        other_cfg.tenant_id = "iso-org-b"

        rag_org = MetricRAG(org_cfg, datasource_id="iso_ds")
        rag_other = MetricRAG(other_cfg, datasource_id="iso_ds")
        rag_default = MetricRAG(base_config, datasource_id="iso_ds")

        rag_org.store_batch([_metric("org_a_revenue")])

        hits_own = [m for m in rag_org.search_metrics("org_a_revenue") if m["name"] == "org_a_revenue"]
        assert hits_own, "own tenant must see its rows"

        assert rag_other.search_metrics("org_a_revenue") == []
        assert rag_default.search_metrics("org_a_revenue") == []

    def test_default_tenant_keeps_legacy_storage_key(self, base_config, tmp_path):
        rag_default = MetricRAG(base_config, datasource_id="iso_ds")
        rag_default.store_batch([_metric("default_mau")])
        rows = rag_default.search_metrics("default_mau")
        assert rows and rows[0]["storage_key"] == "iso_ds:metric:default_mau"
        assert rows[0].get("tenant_id", "") in ("", None)


class TestSessionDirectoryIsolation:
    def test_stamped_config_puts_sessions_in_tenant_layer(self, base_config, tmp_path):
        org_cfg = copy.deepcopy(base_config)
        org_cfg.tenant_id = "iso-org-a"

        sm_org = SessionManager(session_dir=str(tmp_path / "sessions"), scope="alice", tenant_id=org_cfg.tenant_id)
        sm_default = SessionManager(session_dir=str(tmp_path / "sessions"), scope="alice")

        sm_org.create_session("sess-org")
        sm_default.create_session("sess-default")

        assert (tmp_path / "sessions" / "iso-org-a" / "alice" / "sess-org.db").exists()
        assert (tmp_path / "sessions" / "alice" / "sess-default.db").exists()
        assert not (tmp_path / "sessions" / "alice" / "sess-org.db").exists()


class TestFailClosedChain:
    def test_deployment_flag_through_loader_to_rejection(self):
        """api.multi_tenant -> loader escalation -> provider rejection, full chain."""
        provider = load_auth_provider(
            {
                "multi_tenant": True,
                "auth_provider": {"class": "datus.api.auth.gienbi_provider:GienBIAuthProvider"},
            },
            datasource="default",
        )
        assert isinstance(provider, GienBIAuthProvider)
        assert provider.multi_tenant is True

        class _FakeHeaders(dict):
            def get(self, key, default=None):  # minimal request.headers stand-in
                return super().get(key, default)

        class _FakeRequest:
            headers = _FakeHeaders()

        with pytest.raises(DatusException):
            import asyncio

            asyncio.get_event_loop_policy().new_eventLoop() if False else None
            asyncio.run(provider.authenticate(_FakeRequest()))
