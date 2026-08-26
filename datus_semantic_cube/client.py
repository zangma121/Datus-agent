# Copyright 2025-present DatusAI, Inc.
# Licensed under the Apache License, Version 2.0.
# See http://www.apache.org/licenses/LICENSE-2.0 for details.

"""Thin async REST client for Cube.js with per-request tenant JWT auth."""

from typing import Any, Dict, Optional

import httpx

from datus.utils.exceptions import DatusException, ErrorCode
from datus.utils.loggings import get_logger

from datus_semantic_cube.config import CubeConfig
from datus_semantic_cube.token import build_cube_token, resolve_api_secret

logger = get_logger(__name__)


class CubeClient:
    """Call Cube's REST API (``/meta``, ``/load``, ``/sql``).

    The Authorization header is rebuilt per request: adapter instances are
    tenant-scoped, and a passed-through Java token can expire mid-session.
    """

    def __init__(
        self,
        config: CubeConfig,
        http_client: Optional[httpx.AsyncClient] = None,
        passed_through_token: Optional[str] = None,
    ):
        self.config = config
        self._client = http_client
        self._passed_through_token = passed_through_token
        self._meta_cache: Optional[Dict[str, Any]] = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.config.timeout)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    def _auth_headers(self) -> Dict[str, str]:
        token = build_cube_token(
            tenant_id=self.config.tenant_id,
            api_secret=resolve_api_secret(self.config),
            passed_through_token=self._passed_through_token,
        )
        return {"Authorization": f"Bearer {token}"}

    async def _request(self, method: str, path: str, json_body: Optional[dict] = None) -> httpx.Response:
        client = await self._ensure_client()
        url = f"{self.config.api_url.rstrip('/')}{path}"
        try:
            response = await client.request(method, url, json=json_body, headers=self._auth_headers())
        except httpx.HTTPError as exc:
            raise DatusException(
                ErrorCode.SEMANTIC_ADAPTER_ERROR,
                message_args={"error_message": f"Cube request failed ({path}): {exc}"},
            ) from exc

        if response.status_code in (401, 403):
            raise DatusException(
                ErrorCode.SEMANTIC_ADAPTER_ERROR,
                message_args={
                    "error_message": (
                        f"Cube refused the request ({response.status_code} on {path}): "
                        f"{response.text[:200]} — check the tenant JWT (cubeOrgId) and API secret."
                    )
                },
            )
        if response.status_code >= 400:
            raise DatusException(
                ErrorCode.SEMANTIC_ADAPTER_ERROR,
                message_args={"error_message": f"Cube {path} returned {response.status_code}: {response.text[:200]}"},
            )
        return response

    async def get_meta(self, refresh: bool = False) -> Dict[str, Any]:
        """Return (and cache) the ``/meta`` payload for this tenant."""
        if self._meta_cache is None or refresh:
            response = await self._request("GET", "/meta")
            self._meta_cache = response.json()
        return self._meta_cache

    async def load(self, query: Dict[str, Any]) -> Dict[str, Any]:
        response = await self._request("POST", "/load", json_body={"query": query})
        return response.json()

    async def sql(self, query: Dict[str, Any]) -> Dict[str, Any]:
        response = await self._request("POST", "/sql", json_body={"query": query})
        return response.json()
