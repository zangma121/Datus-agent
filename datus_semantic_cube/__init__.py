# Copyright 2025-present DatusAI, Inc.
# Licensed under the Apache License, Version 2.0.
# See http://www.apache.org/licenses/LICENSE-2.0 for details.

"""Cube.js semantic layer adapter for Datus (datus-agent-cube M2).

Implements the ``datus_semantic_core`` adapter interface against Cube's REST
API (``/meta``, ``/load``, ``/sql``), with per-tenant JWT auth following the
GienBI/Java ``cubeOrgId = orgId + "A"`` convention.
"""

from datus_semantic_cube.adapter import CubeAdapter
from datus_semantic_cube.config import CubeConfig

__all__ = ["CubeAdapter", "CubeConfig", "register"]


def register() -> None:
    """Register the cube adapter with the Datus semantic adapter registry."""
    from datus.tools.semantic_tools import semantic_adapter_registry

    semantic_adapter_registry.register(
        service_type="cube",
        adapter_class=CubeAdapter,
        config_class=CubeConfig,
        display_name="Cube",
    )
