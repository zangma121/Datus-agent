"""Live integration tests for the Cube adapter (M2, T2.6).

Runs against a real Cube deployment when ``CUBE_LIVE_URL`` is set
(single-tenant upstream Cube with the orders fixture — see
design/datus-agent-cube-plan.md T2.6 for the docker one-liner);
otherwise skipped so CI without the fixture stays green.

Multi-tenant (cubeOrgId) verification additionally needs GienBI's bank
stack and is intentionally NOT covered here.
"""

import os

import pytest

pytestmark = pytest.mark.integration

LIVE_URL = os.environ.get("CUBE_LIVE_URL", "").rstrip("/")
LIVE_SECRET = os.environ.get("CUBE_LIVE_SECRET", "")


def _live():
    if not (LIVE_URL and LIVE_SECRET):
        pytest.skip("CUBE_LIVE_URL / CUBE_LIVE_SECRET not set; live cube fixture unavailable")
    from datus_semantic_cube.adapter import CubeAdapter
    from datus_semantic_cube.config import CubeConfig

    os.environ["CUBEJS_API_SECRET"] = LIVE_SECRET
    config = CubeConfig(datasource="cube_live", api_url=f"{LIVE_URL}/cubejs-api/v1", timeout=60)
    return CubeAdapter(config)


def test_live_meta_lists_orders_measures():
    import asyncio

    adapter = _live()
    metrics = asyncio.run(adapter.list_metrics())
    names = {m.name for m in metrics}
    assert "Orders.count" in names
    assert "Orders.totalAmount" in names


def test_live_dimensions_for_metric():
    adapter = _live()
    dims = asyncio_run(adapter.get_dimensions("Orders.totalAmount"))
    names = {d.name for d in dims}
    assert {"Orders.status", "Orders.region", "Orders.createdAt"} <= names


def test_live_query_returns_rows():
    adapter = _live()
    result = asyncio_run(
        adapter.query_metrics(metrics=["Orders.count"], dimensions=["Orders.region"], order_by=["Orders.region"])
    )
    assert result.columns == ["Orders.region", "Orders.count"]
    # Cube JSON-serializes numbers as strings; compare numerically.
    rows_by_region = {r["Orders.region"]: int(r["Orders.count"]) for r in result.data}
    assert rows_by_region == {"east": 3, "west": 2}


def test_live_dry_run_returns_sql():
    adapter = _live()
    result = asyncio_run(adapter.query_metrics(metrics=["Orders.totalAmount"], dry_run=True))
    assert "SELECT" in result.metadata["sql"].upper()
    assert "orders" in result.metadata["sql"].lower()


def test_live_validate_semantic():
    adapter = _live()
    result = asyncio_run(adapter.validate_semantic())
    assert result.valid is True


import asyncio


def asyncio_run(coro):
    return asyncio.run(coro)
