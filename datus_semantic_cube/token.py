# Copyright 2025-present DatusAI, Inc.
# Licensed under the Apache License, Version 2.0.
# See http://www.apache.org/licenses/LICENSE-2.0 for details.

"""Cube JWT auth, aligned with the GienBI Java/chat2agent convention.

The Java backend issues Cube tokens itself; when it forwards one we pass it
through untouched. Otherwise we self-sign an HS256 token whose
``cubeOrgId = {tenant}A`` claim maps to Cube's per-tenant
``model/{metaOrgId}/`` directories. The shared secret only ever enters
through an environment variable.
"""

import os
import time
from typing import Optional

import jwt as pyjwt

from datus.utils.exceptions import DatusException, ErrorCode

#: chat2agent ``query_execute.py`` / Java ``CubeHttpUtils`` convention.
_CUBE_META_ORG_SUFFIX = "A"

#: Token lifetime in seconds; matches chat2agent's 30-minute window.
_TOKEN_TTL_SECONDS = 1800


def resolve_api_secret(config) -> str:
    """Read the Cube API secret from the configured environment variable."""
    return os.environ.get(config.api_secret_env, "")


def build_cube_token(
    tenant_id: Optional[str],
    api_secret: str,
    passed_through_token: Optional[str] = None,
) -> str:
    """Return the JWT to send as the Cube Authorization bearer token.

    Priority: a pre-issued (Java) token passed through > a freshly self-signed
    token. Fails closed when neither is possible: without a secret we cannot
    authenticate to Cube at all, and an unauthenticated request would leak
    whatever the deployment's defaults allow.
    """
    if passed_through_token:
        return passed_through_token

    tenant = str(tenant_id or "").strip()
    if not api_secret:
        raise DatusException(
            ErrorCode.COMMON_CONFIG_ERROR,
            message=(
                "Cube adapter cannot authenticate: no passed-through cube_token and "
                "no API secret (set CUBEJS_API_SECRET or the configured env var)."
            ),
        )

    now = int(time.time())
    payload: dict = {"iat": now, "exp": now + _TOKEN_TTL_SECONDS}
    if tenant:
        # Multi-tenant Cube: the claim routes to model/{metaOrgId}/ dirs.
        payload["cubeOrgId"] = f"{tenant}{_CUBE_META_ORG_SUFFIX}"
    # Single-tenant Cube accepts any correctly-signed token; no org claim.
    return pyjwt.encode(payload, api_secret, algorithm="HS256")
