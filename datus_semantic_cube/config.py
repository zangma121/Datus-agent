# Copyright 2025-present DatusAI, Inc.
# Licensed under the Apache License, Version 2.0.
# See http://www.apache.org/licenses/LICENSE-2.0 for details.

"""Configuration for the Cube semantic adapter."""

from typing import Optional

from pydantic import BaseModel, Field


class CubeConfig(BaseModel):
    """Settings for talking to a Cube.js deployment.

    The API secret is referenced by environment-variable name only — never
    inline the secret in agent.yml (it would end up in config backups).
    ``tenant_id`` (GienBI org) is injected per request by the adapter
    factory; each tenant gets its own JWT claims (``cubeOrgId``).
    """

    service_type: str = "cube"
    datasource: str = Field(..., description="Datus datasource this semantic layer serves")
    api_url: str = Field(default="http://localhost:4000/cubejs-api/v1")
    api_secret_env: str = Field(default="CUBEJS_API_SECRET")
    timeout: int = Field(default=60, description="Request timeout in seconds")
    timezone: str = Field(default="UTC")
    tenant_id: Optional[str] = Field(default=None)

    class Config:
        extra = "allow"
