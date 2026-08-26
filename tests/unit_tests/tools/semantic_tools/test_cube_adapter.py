"""Spec for the in-tree Cube semantic adapter (datus-agent-cube M2, T2.1).

``datus_semantic_cube`` registers itself as the ``cube`` service type in the
semantic adapter registry, with a config that carries the Cube REST endpoint
and JWT settings. Registration is idempotent so repeated imports are safe.
"""

import pytest

from datus_semantic_cube import CubeConfig, register
from datus.tools.semantic_tools import semantic_adapter_registry


@pytest.fixture(autouse=True)
def _cube_test_secret(monkeypatch):
    """Every adapter call signs a JWT; give the tests a deterministic secret."""
    monkeypatch.setenv("CUBEJS_API_SECRET", "test-secret")


class TestCubeRegistration:
    def test_register_adds_cube_service_type(self):
        register()
        assert semantic_adapter_registry.is_registered("cube")
        metadata = semantic_adapter_registry.get_metadata("cube")
        assert metadata is not None
        assert metadata.config_class is CubeConfig

    def test_register_is_idempotent(self):
        register()
        register()
        assert semantic_adapter_registry.is_registered("cube")


class TestCubeConfig:
    def test_minimal_config(self):
        cfg = CubeConfig(datasource="bank")
        assert cfg.service_type == "cube"
        assert cfg.api_url == "http://localhost:4000/cubejs-api/v1"
        assert cfg.timeout == 60
        assert cfg.api_secret_env == "CUBEJS_API_SECRET"

    def test_custom_config(self):
        cfg = CubeConfig(
            datasource="bank",
            api_url="https://cube.example.com/cubejs-api/v1",
            timeout=30,
        )
        assert cfg.api_url == "https://cube.example.com/cubejs-api/v1"
        assert cfg.timeout == 30

    def test_tenant_from_context(self):
        """Per-request tenant scoping: the adapter factory injects tenant_id
        (GienBI org) so each instance builds its own Cube JWT claims."""
        cfg = CubeConfig(datasource="bank", tenant_id="org-42")
        assert cfg.tenant_id == "org-42"


class TestCubeToken:
    """T2.2: JWT auth following the chat2agent/Java convention.

    Priority: a Java-issued token passed through ``cube_token`` wins; with no
    token but a secret available, self-sign HS256 with ``cubeOrgId`` =
    ``{tenant}A`` and a bounded ``exp``; with neither, raise (fail closed).
    """

    def test_passthrough_token_wins(self):
        from datus_semantic_cube.token import build_cube_token

        token = build_cube_token(
            tenant_id="org-42",
            api_secret="secret",
            passed_through_token="java-issued-token",
        )
        assert token == "java-issued-token"

    def test_self_signed_token_claims(self):
        import time

        import jwt as pyjwt

        from datus_semantic_cube.token import build_cube_token

        before = int(time.time())
        token = build_cube_token(tenant_id="org-42", api_secret="secret")
        payload = pyjwt.decode(token, "secret", algorithms=["HS256"])
        assert payload["cubeOrgId"] == "org-42A"
        assert before <= payload["iat"] <= payload["exp"]
        assert payload["exp"] - payload["iat"] <= 1800

    def test_no_token_no_secret_fails_closed(self):
        import pytest

        from datus_semantic_cube.token import build_cube_token
        from datus.utils.exceptions import DatusException

        with pytest.raises(DatusException):
            build_cube_token(tenant_id="org-42", api_secret="")

    def test_secret_read_from_env(self, monkeypatch):
        from datus_semantic_cube.config import CubeConfig
        from datus_semantic_cube.token import resolve_api_secret

        monkeypatch.setenv("CUBEJS_API_SECRET", "env-secret")
        assert resolve_api_secret(CubeConfig(datasource="bank")) == "env-secret"

        monkeypatch.delenv("CUBEJS_API_SECRET")
        assert resolve_api_secret(CubeConfig(datasource="bank")) == ""


def _meta_payload():
    """A trimmed but shape-faithful Cube /meta response."""
    return {
        "cubes": [
            {
                "name": "Orders",
                "title": "Orders",
                "measures": [
                    {"name": "Orders.count", "title": "Order Count", "type": "count"},
                    {
                        "name": "Orders.totalAmount",
                        "title": "Total Amount",
                        "type": "sum",
                        "description": "Sum of order amounts",
                    },
                ],
                "dimensions": [
                    {"name": "Orders.status", "type": "string", "title": "Status"},
                    {"name": "Orders.createdAt", "type": "time", "title": "Created At"},
                ],
            },
            {
                "name": "Users",
                "title": "Users",
                "measures": [{"name": "Users.activeCount", "title": "Active Users"}],
                "dimensions": [{"name": "Users.country", "type": "string"}],
            },
        ]
    }


def _adapter_with_meta(payload=None, requests=None):
    import httpx

    from datus_semantic_cube.adapter import CubeAdapter
    from datus_semantic_cube.config import CubeConfig

    payload = payload if payload is not None else _meta_payload()

    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        if request.url.path.endswith("/meta"):
            return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"error": "not found"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    from datus_semantic_cube.client import CubeClient

    config = CubeConfig(datasource="bank", api_url="http://cube.local/cubejs-api/v1")
    return CubeAdapter(config, client=CubeClient(config, http_client=http_client))


@pytest.mark.asyncio
class TestListMetrics:
    async def test_measures_become_metric_definitions(self):
        adapter = _adapter_with_meta()
        metrics = await adapter.list_metrics()
        names = {m.name for m in metrics}
        assert names == {"Orders.count", "Orders.totalAmount", "Users.activeCount"}
        amount = next(m for m in metrics if m.name == "Orders.totalAmount")
        assert "Sum of order amounts" in (amount.description or "")
        assert "Orders.status" in (amount.dimensions or [])

    async def test_path_filters_by_cube(self):
        adapter = _adapter_with_meta()
        metrics = await adapter.list_metrics(path=["Users"])
        assert [m.name for m in metrics] == ["Users.activeCount"]

    async def test_pagination(self):
        adapter = _adapter_with_meta()
        page = await adapter.list_metrics(limit=2, offset=1)
        assert len(page) == 2

    async def test_auth_header_is_bearer_jwt(self):
        import jwt as pyjwt

        requests = []
        adapter = _adapter_with_meta(requests=requests)
        adapter.cube_config.tenant_id = "org-42"
        await adapter.list_metrics(limit=1)
        auth = requests[0].headers["Authorization"]
        assert auth.startswith("Bearer ")
        payload = pyjwt.decode(auth.removeprefix("Bearer "), "ignored", algorithms=["HS256"],
                               options={"verify_signature": False})
        assert payload["cubeOrgId"] == "org-42A"


@pytest.mark.asyncio
class TestGetDimensions:
    async def test_dimensions_for_metric_cube(self):
        adapter = _adapter_with_meta()
        dims = await adapter.get_dimensions("Orders.totalAmount")
        names = {d.name for d in dims}
        assert names == {"Orders.status", "Orders.createdAt"}
        time_dim = next(d for d in dims if d.name == "Orders.createdAt")
        assert d_is_time(time_dim)

    async def test_unknown_metric_returns_empty(self):
        adapter = _adapter_with_meta()
        assert await adapter.get_dimensions("Nope.measure") == []


def d_is_time(dim) -> bool:
    return dim.is_primary_time or "time" in (dim.type or "")


def _adapter_with_routes(routes, requests=None):
    """routes: dict of path-suffix -> json payload."""
    import httpx

    from datus_semantic_cube.adapter import CubeAdapter
    from datus_semantic_cube.client import CubeClient
    from datus_semantic_cube.config import CubeConfig

    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        for suffix, payload in routes.items():
            if request.url.path.endswith(suffix):
                return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"error": f"unexpected {request.url.path}"})

    config = CubeConfig(datasource="bank", api_url="http://cube.local/cubejs-api/v1")
    return CubeAdapter(config, client=CubeClient(config, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))))


@pytest.mark.asyncio
class TestQueryMetrics:
    async def test_load_result_mapped_to_query_result(self):
        adapter = _adapter_with_routes({
            "/load": {"data": [
                {"Orders.status": "completed", "Orders.count": 7},
                {"Orders.status": "open", "Orders.count": 3},
            ]},
        })
        result = await adapter.query_metrics(
            metrics=["Orders.count"], dimensions=["Orders.status"], limit=10
        )
        assert result.columns == ["Orders.status", "Orders.count"]
        assert len(result.data) == 2
        assert result.data[0]["Orders.count"] == 7

    async def test_query_payload_shape(self):
        requests = []
        adapter = _adapter_with_routes({
            "/meta": _meta_payload(),
            "/load": {"data": []},
        }, requests=requests)
        await adapter.query_metrics(
            metrics=["Orders.count"],
            dimensions=["Orders.status"],
            time_start="2024-01-01",
            time_end="2024-12-31",
            where="Orders.status = 'completed'",
            limit=5,
        )
        body = requests[-1].read()
        import json

        query = json.loads(body)["query"]
        assert query["measures"] == ["Orders.count"]
        assert query["dimensions"] == ["Orders.status"]
        assert query["limit"] == 5
        assert query["filters"] == [
            {"member": "Orders.status", "operator": "equals", "values": ["completed"]}
        ]
        time_dims = query["timeDimensions"]
        assert len(time_dims) == 1
        assert time_dims[0]["dimension"] == "Orders.createdAt"
        assert time_dims[0]["dateRange"] == ["2024-01-01", "2024-12-31"]

    async def test_dry_run_returns_compiled_sql(self):
        adapter = _adapter_with_routes({
            "/meta": _meta_payload(),
            "/sql": {"sql": ["SELECT count(*) FROM orders WHERE status = ?", ["completed"]]},
        })
        result = await adapter.query_metrics(metrics=["Orders.count"], dry_run=True)
        assert "SELECT count(*)" in result.metadata["sql"]

    async def test_empty_result(self):
        adapter = _adapter_with_routes({"/load": {"data": []}})
        result = await adapter.query_metrics(metrics=["Orders.count"])
        assert result.data == []
        assert result.columns == []


class TestValidateAndModels:
    async def test_validate_meta_reachable(self):
        adapter = _adapter_with_meta()
        result = await adapter.validate_semantic()
        assert result.valid is True
        assert result.issues == []

    async def test_validate_meta_unreachable(self):
        from datus.utils.exceptions import DatusException

        adapter = _adapter_with_routes({"/nope": {}})
        with pytest.raises(DatusException):
            await adapter.validate_semantic()

    def test_cubes_listed_as_semantic_models(self):
        adapter = _adapter_with_meta()
        models = adapter.list_semantic_models()  # sync per interface contract
        assert [m.name for m in models] == ["Orders", "Users"]

    def test_single_model_lookup(self):
        adapter = _adapter_with_meta()
        model = adapter.get_semantic_model("Users")
        assert model is not None
        assert model.name == "Users"
        assert adapter.get_semantic_model("Missing") is None


class TestAdapterFactoryWiring:
    """T3.4: the real creation path — agent config -> adapter config ->
    registry factory -> CubeAdapter (no live Cube needed)."""

    def test_registry_creates_cube_adapter_from_config_dict(self):
        from datus_semantic_cube import register
        from datus_semantic_cube.adapter import CubeAdapter
        from datus_semantic_cube.config import CubeConfig
        from datus.tools.semantic_tools import semantic_adapter_registry

        register()
        metadata = semantic_adapter_registry.get_metadata("cube")
        assert metadata is not None and metadata.config_class is CubeConfig

        config = CubeConfig(datasource="bank", api_url="http://cube.local/cubejs-api/v1")
        adapter = semantic_adapter_registry.create_adapter("cube", config)
        assert isinstance(adapter, CubeAdapter)
        assert adapter.cube_config.api_url == "http://cube.local/cubejs-api/v1"


@pytest.mark.asyncio
class TestRowFilterInjection:
    """M4.5 review fix: policy row_filters reach the Cube query payload."""

    async def test_injected_filters_merge_into_query(self):
        requests = []
        adapter = _adapter_with_routes({
            "/meta": _meta_payload(),
            "/load": {"data": []},
        }, requests=requests)
        adapter.inject_row_filters([{"member": "Orders.region", "operator": "equals", "values": ["east"]}])
        await adapter.query_metrics(metrics=["Orders.count"])
        import json

        body = json.loads(requests[-1].read())
        filters = body["query"]["filters"]
        assert {"member": "Orders.region", "operator": "equals", "values": ["east"]} in filters

    async def test_no_injection_keeps_payload_clean(self):
        requests = []
        adapter = _adapter_with_routes({"/load": {"data": []}}, requests=requests)
        await adapter.query_metrics(metrics=["Orders.count"])
        import json

        body = json.loads(requests[-1].read())
        assert "filters" not in body["query"]
