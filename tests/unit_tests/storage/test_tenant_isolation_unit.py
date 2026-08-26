"""Cross-tenant invisibility for embedding stores (M1b T1.5 vertical slice).

Two MetricStorage instances sharing the physical table and datasource_id but
differing only in tenant_id must not see each other's rows; the default
tenant keeps seeing the legacy-format rows.
"""

import pytest

from datus.storage.embedding_models import get_metric_embedding_model
from datus.storage.metric.store import MetricStorage


def _store(tenant_id: str | None) -> MetricStorage:
    kwargs = {"datasource_id": "ds1"}
    if tenant_id is not None:
        kwargs["tenant_id"] = tenant_id
    return MetricStorage(embedding_model=get_metric_embedding_model(), **kwargs)


def _metric(name: str) -> dict:
    return {
        "id": f"metric:{name}",
        "name": name,
        "description": f"description of {name}",
        "subject_path": ["Test"],
        "metric_type": "simple",
        "datasource_id": "ds1",
    }


@pytest.fixture
def _clean_table():
    store = _store(None)
    if store.db.table_exists(store.table_name):
        store.db.drop_table(store.table_name)
    yield
    if store.db.table_exists(store.table_name):
        store.db.drop_table(store.table_name)


@pytest.mark.usefixtures("_clean_table")
class TestCrossTenantIsolation:
    def test_tenant_rows_invisible_to_other_tenant_and_default(self):
        tenant_a = _store("org-a")
        tenant_a.batch_store_metrics([_metric("dau")])

        # Own tenant sees its row
        assert len(tenant_a.search_metrics("dau", top_n=5)) >= 1

        # A different tenant sees nothing
        tenant_b = _store("org-b")
        assert tenant_b.search_metrics("dau", top_n=5) == []

        # The default tenant does not see tenant-a rows
        default_tenant = _store(None)
        assert default_tenant.search_metrics("dau", top_n=5) == []

    def test_default_tenant_rows_use_legacy_keys(self):
        default_tenant = _store(None)
        default_tenant.batch_store_metrics([_metric("mau")])
        rows = default_tenant.search_metrics("mau", top_n=5)
        assert len(rows) == 1
        # Legacy format (no tenant prefix) keeps existing rows addressable.
        assert rows[0]["storage_key"] == "ds1:metric:mau"
        assert rows[0].get("tenant_id", "") in ("", None)
