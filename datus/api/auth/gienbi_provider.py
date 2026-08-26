"""GienBI auth provider — trusted-header identity from the GienBI Java gateway.

GienBI's Java backend (Datart) authenticates end users and forwards identity
to Datus over internal headers; Datus itself does not verify user
credentials (inner-service trust, same posture as chat2agent). The provider
only validates presence and format:

- ``X-GienBI-OrgId``   → ``AppContext.tenant_id`` (first-class tenant boundary)
- ``X-GienBI-UserId``  → ``AppContext.user_id`` (``SessionManager.scope``)
- ``X-GienBI-AgentId`` → ``AppContext.sub_agent_name`` (KB read boundary; must
  be an ``agentic_nodes`` key — unknown names are rejected downstream by
  ``get_scoped_sub_agent`` with 400, before any scoped read)
- ``X-GienBI-CubeToken`` → optional pre-issued Cube JWT, passed through to the
  Cube adapter via ``policy_context``

``policy_context`` additionally carries ``gienbi_org_id`` / ``gienbi_user_id``
/ ``gienbi_agent_id`` for the gienbi-policy plugin and ``cube_org_id``
following the chat2agent/Java ``metaOrgId = orgId + "A"`` convention (maps to
Cube's ``model/{metaOrgId}/`` tenant directories).

With ``multi_tenant=True`` the provider fails closed: a request without both
org and user identity is rejected instead of silently becoming anonymous.
"""

import re
from typing import Any

from fastapi import Request

from datus.api.auth.context import AppContext
from datus.api.auth.provider import EvictCallback
from datus.utils.exceptions import DatusException, ErrorCode
from datus.utils.loggings import get_logger

logger = get_logger(__name__)

HEADER_GIENBI_ORG_ID = "X-GienBI-OrgId"
HEADER_GIENBI_USER_ID = "X-GienBI-UserId"
HEADER_GIENBI_AGENT_ID = "X-GienBI-AgentId"
HEADER_GIENBI_CUBE_TOKEN = "X-GienBI-CubeToken"

# Same character policy as the open-source user_id header: values end up in
# filesystem paths (session directories) and storage keys.
_GIENBI_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

# chat2agent/Java CubeHttpUtils convention: metaOrgId = orgId + "A".
_CUBE_META_ORG_SUFFIX = "A"


def _cube_org_id(org_id: str) -> str:
    return f"{org_id}{_CUBE_META_ORG_SUFFIX}"


class GienBIAuthProvider:
    """Map trusted GienBI gateway headers onto ``AppContext``.

    ``multi_tenant`` mirrors ``agent.multi_tenant`` from the agent config and
    is injected by the provider loader; the provider itself never reads
    configuration so it stays trivially testable.
    """

    def __init__(self, multi_tenant: bool = False) -> None:
        self.multi_tenant = multi_tenant
        self._evict_callbacks: list[EvictCallback] = []

    async def authenticate(self, request: Request) -> AppContext:
        org_id = self._read_id(request, HEADER_GIENBI_ORG_ID)
        user_id = self._read_id(request, HEADER_GIENBI_USER_ID)
        agent_id = self._read_id(request, HEADER_GIENBI_AGENT_ID, optional=True)
        cube_token = self._read_optional(request, HEADER_GIENBI_CUBE_TOKEN)

        if self.multi_tenant and (not org_id or not user_id):
            raise DatusException(
                ErrorCode.COMMON_VALIDATION_FAILED,
                message=(
                    "Multi-tenant deployment requires both "
                    f"{HEADER_GIENBI_ORG_ID} and {HEADER_GIENBI_USER_ID} headers."
                ),
            )

        if not org_id or not user_id:
            # Single-tenant mode without headers: anonymous, default tenant.
            return AppContext(tenant_id=None, user_id=None, policy_context={})

        policy_context: dict[str, Any] = {
            "gienbi_org_id": org_id,
            "gienbi_user_id": user_id,
            "cube_org_id": _cube_org_id(org_id),
        }
        if agent_id:
            policy_context["gienbi_agent_id"] = agent_id
        if cube_token:
            policy_context["cube_token"] = cube_token

        return AppContext(
            tenant_id=org_id,
            user_id=user_id,
            sub_agent_name=agent_id,
            policy_context=policy_context,
        )

    def on_evict(self, callback: EvictCallback) -> None:
        """Register an eviction callback for the provider lifecycle."""
        self._evict_callbacks.append(callback)

    @staticmethod
    def _read_optional(request: Request, header: str) -> str | None:
        raw = request.headers.get(header)
        if raw is None:
            return None
        candidate = raw.strip()
        return candidate or None

    def _read_id(self, request: Request, header: str, optional: bool = False) -> str | None:
        candidate = self._read_optional(request, header)
        if candidate is None:
            return None
        if not _GIENBI_ID_PATTERN.match(candidate):
            raise DatusException(
                ErrorCode.COMMON_VALIDATION_FAILED,
                message=(
                    f"Invalid {header} header value: {candidate!r}. "
                    "Only letters, digits, underscore and hyphen are allowed."
                ),
            )
        return candidate
