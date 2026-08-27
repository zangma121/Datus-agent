# Copyright 2025-present DatusAI, Inc.
# Licensed under the Apache License, Version 2.0.
# See http://www.apache.org/licenses/LICENSE-2.0 for details.

"""Cube.js adapter implementing the Datus semantic adapter interface.

Mapping: Cube ``cubes`` → semantic models, cube ``measures`` → metrics,
cube ``dimensions`` → dimensions. ``path`` filters by cube name (the Cube
equivalent of a dataset). Queries go to ``POST /load`` (execution) or
``POST /sql`` (dry-run explain).
"""

from typing import List, Optional

import httpx
import re

from datus_semantic_core.base import BaseSemanticAdapter
from datus_semantic_core.models import (
    DimensionInfo,
    MetricDefinition,
    QueryResult,
    ValidationResult,
)
from datus.utils.exceptions import DatusException, ErrorCode
from datus.utils.loggings import get_logger

from datus_semantic_cube.client import CubeClient
from datus_semantic_cube.config import CubeConfig

logger = get_logger(__name__)

#: Granularities Cube time dimensions accept, finest → coarsest.
_TIME_GRANULARITIES = ["second", "minute", "hour", "day", "week", "month", "quarter", "year"]

#: ``member = 'value'`` → equals; ``member IN ('a','b')`` → in;
#: ``member OP number-or-'string'`` (=/!=/>/>=/</<=) → comparison operators.
_WHERE_EQ_RE = re.compile(r"^\s*([A-Za-z0-9_.]+)\s*=\s*'([^']*)'\s*$")
_WHERE_NE_RE = re.compile(r"^\s*([A-Za-z0-9_.]+)\s*!=\s*'([^']*)'\s*$")
_WHERE_IN_RE = re.compile(r"^\s*([A-Za-z0-9_.]+)\s+IN\s*\(([^)]*)\)\s*$", re.IGNORECASE)
_WHERE_CMP_RE = re.compile(r"^\s*([A-Za-z0-9_.]+)\s*(>=|<=|>|<)\s*([A-Za-z0-9_.-]+)\s*$")

_CMP_OPS = {">": "gt", ">=": "gte", "<": "lt", "<=": "lte"}


def _parse_where_filter(where: str) -> dict:
    match = _WHERE_EQ_RE.match(where)
    if match:
        return {"member": match.group(1), "operator": "equals", "values": [match.group(2)]}
    match = _WHERE_NE_RE.match(where)
    if match:
        return {"member": match.group(1), "operator": "notEquals", "values": [match.group(2)]}
    match = _WHERE_IN_RE.match(where)
    if match:
        values = [v.strip().strip("'\"") for v in match.group(2).split(",") if v.strip()]
        return {"member": match.group(1), "operator": "in", "values": values}
    match = _WHERE_CMP_RE.match(where)
    if match:
        return {"member": match.group(1), "operator": _CMP_OPS[match.group(2)], "values": [match.group(3)]}
    raise DatusException(
        ErrorCode.SEMANTIC_ADAPTER_ERROR,
        message_args={
            "error_message": (
                f"Cube adapter supports equality, IN lists and simple comparisons in "
                f"`where` (e.g. \"Cube.dim = 'v'\" / \"Cube.dim IN ('a','b')\" / "
                f"\"Cube.measure > 500\"), got: {where!r}."
            )
        },
    )


class CubeAdapter(BaseSemanticAdapter):
    """Translate the Datus semantic interface onto Cube's REST API."""

    def __init__(self, config: CubeConfig, client: Optional[CubeClient] = None):
        super().__init__(config, service_type="cube")
        self.cube_config = config
        self.client = client or CubeClient(config)
        # Row-level policy filters injected by the policy runtime (M4.5);
        # merged into every query payload until cleared.
        self._row_filters: List[dict] = []

    def inject_row_filters(self, filters: List[dict]) -> None:
        """Accept row-scope filters exported by the policy runtime.

        The gienbi-policy plugin computes them from GienBI row-permission
        scripts; the adapter merges them into the query payload so row
        scope is enforced inside Cube, not by rewriting SQL.
        """
        self._row_filters = list(filters or [])
        logger.info("Cube adapter received %d row-scope filters", len(self._row_filters))

    # ── /meta helpers ────────────────────────────────────────────────

    async def _cubes(self, path: Optional[List[str]] = None) -> List[dict]:
        meta = await self.client.get_meta()
        cubes = meta.get("cubes") or []
        if path:
            wanted = {str(p) for p in path}
            cubes = [c for c in cubes if c.get("name") in wanted]
        return cubes

    @staticmethod
    def _cube_for_member(cubes: List[dict], member_name: str) -> Optional[dict]:
        prefix = f"{member_name.split('.')[0]}." if "." in member_name else ""
        if not prefix:
            return None
        cube_name = prefix[:-1]
        for cube in cubes:
            if cube.get("name") == cube_name:
                return cube
        return None

    # ── Metrics interface ────────────────────────────────────────────

    async def list_metrics(
        self,
        path: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[MetricDefinition]:
        cubes = await self._cubes(path)
        metrics: List[MetricDefinition] = []
        for cube in cubes:
            cube_name = cube.get("name") or ""
            dimension_names = [d.get("name") or "" for d in cube.get("dimensions") or []]
            for measure in cube.get("measures") or []:
                metrics.append(
                    MetricDefinition(
                        name=measure.get("name") or "",
                        description=measure.get("description") or measure.get("title") or "",
                        type=measure.get("type") or "",
                        dimensions=dimension_names,
                        path=[cube_name],
                        metadata={"cube": cube_name, "agg_type": measure.get("aggType")},
                    )
                )
        return metrics[offset : offset + limit]

    async def get_dimensions(
        self,
        metric_name: str,
        path: Optional[List[str]] = None,
    ) -> List[DimensionInfo]:
        cubes = await self._cubes(path)
        cube = self._cube_for_member(cubes, metric_name)
        if cube is None:
            return []
        dims: List[DimensionInfo] = []
        for dim in cube.get("dimensions") or []:
            is_time = (dim.get("type") or "") == "time"
            info = DimensionInfo(
                name=dim.get("name") or "",
                description=dim.get("title") or dim.get("description") or "",
                type=dim.get("type") or "string",
                is_primary_time=is_time,
            )
            if is_time:
                info.time_granularities = list(_TIME_GRANULARITIES)
            dims.append(info)
        return dims

    async def query_metrics(
        self,
        metrics: List[str],
        dimensions: Optional[List[str]] = None,
        path: Optional[List[str]] = None,
        time_start: Optional[str] = None,
        time_end: Optional[str] = None,
        time_granularity: Optional[str] = None,
        where: Optional[str] = None,
        limit: Optional[int] = None,
        order_by: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> QueryResult:
        query: dict = {"measures": list(metrics)}
        if dimensions:
            query["dimensions"] = list(dimensions)

        if time_start or time_end or time_granularity:
            time_dim = await self._primary_time_dimension(metrics + (dimensions or []))
            if time_dim is None:
                raise DatusException(
                    ErrorCode.SEMANTIC_ADAPTER_ERROR,
                    message_args={
                        "error_message": (
                            "Cube query has a time range but no time dimension was found "
                            "in the involved cubes' /meta."
                        )
                    },
                )
            entry: dict = {"dimension": time_dim}
            if time_start or time_end:
                entry["dateRange"] = [time_start or "", time_end or ""]
            if time_granularity:
                entry["granularity"] = time_granularity
            query["timeDimensions"] = [entry]

        filters: List[dict] = []
        if where:
            filters.append(_parse_where_filter(where))
        # Row-scope filters from the policy runtime ride along on every
        # query (AND-combined with any user where).
        filters.extend(self._row_filters)
        if filters:
            query["filters"] = filters
        if limit is not None:
            query["limit"] = int(limit)
        if order_by:
            order: dict = {}
            for item in order_by:
                item = str(item).strip()
                if item.startswith("-"):
                    # Interface convention: '-member' means descending.
                    order[item[1:].strip()] = "desc"
                    continue
                name, _, direction = item.rpartition(" ")
                if direction.lower() in ("asc", "desc"):
                    order[name.strip()] = direction.lower()
                else:
                    order[item] = "asc"
            query["order"] = order

        if dry_run:
            payload = await self.client.sql(query)
            # /sql response shape varies by Cube version: the SQL parts array
            # sits either at the top level or nested under "sql".
            sql_payload = payload.get("sql")
            if isinstance(sql_payload, dict):
                sql_payload = sql_payload.get("sql")
            sql_parts = sql_payload if isinstance(sql_payload, list) else []
            return QueryResult(
                columns=[],
                data=[],
                metadata={"sql": sql_parts[0] if sql_parts else "", "params": sql_parts[1] if len(sql_parts) > 1 else []},
            )

        payload = await self.client.load(query)
        rows = payload.get("data") or []
        columns = list(rows[0].keys()) if rows else []
        return QueryResult(columns=columns, data=rows, metadata={})

    async def _primary_time_dimension(self, members: List[str]) -> Optional[str]:
        """Find the first TIME dimension among the cubes referenced by members."""
        cubes = await self._cubes()
        seen: set = set()
        for member in members:
            cube = self._cube_for_member(cubes, member)
            if cube is None or cube.get("name") in seen:
                continue
            seen.add(cube.get("name"))
            for dim in cube.get("dimensions") or []:
                if (dim.get("type") or "") == "time":
                    return dim.get("name")
        return None

    async def validate_semantic(self, scope: str = "all") -> ValidationResult:
        """/meta reachability is the health check: a broken model set or a
        bad JWT fails here before any query."""
        await self.client.get_meta(refresh=True)
        return ValidationResult(valid=True, issues=[])

    # ── Semantic model interface (cubes) — SYNC per the interface contract ──

    def list_semantic_models(
        self,
        catalog_name: str = "",
        database_name: str = "",
        schema_name: str = "",
    ) -> list:
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            # Called from async context: run in a worker thread with its own
            # loop (BaseSemanticAdapter keeps this method sync by contract).
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(
                    lambda: asyncio.run(self._list_semantic_models_async())
                ).result()
        return asyncio.run(self._list_semantic_models_async())

    def get_semantic_model(
        self,
        table_name: str,
        catalog_name: str = "",
        database_name: str = "",
        schema_name: str = "",
    ):
        for model in self.list_semantic_models():
            if model.name == table_name:
                return model
        return None

    async def _list_semantic_models_async(self) -> list:
        cubes = await self._cubes()
        return [self._model_info(cube) for cube in cubes]

    @staticmethod
    def _model_info(cube: dict):
        from datus_semantic_core.models import SemanticModelInfo

        # storage_sync requires a physical table name; derive it from the
        # cube's sql (``SELECT * FROM orders``) and fall back to cube name.
        table_name = cube.get("name") or ""
        sql = str(cube.get("sql") or "")
        if sql:
            match = re.search(r"from\s+([A-Za-z_][A-Za-z0-9_.]*)", sql, re.IGNORECASE)
            if match:
                table_name = match.group(1)
        return SemanticModelInfo(
            name=cube.get("name") or "",
            description=cube.get("title") or cube.get("description") or "",
            table_name=table_name,
            dimensions=[
                DimensionInfo(name=d.get("name") or "", type=d.get("type") or "string")
                for d in cube.get("dimensions") or []
            ],
            measures=[
                m.get("name") or "" for m in cube.get("measures") or []
            ],
            platform_type="cube",
        )
