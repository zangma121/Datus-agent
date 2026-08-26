"""Spec for the GienBI auth provider (datus-agent-cube M1a).

GienBI's Java gateway (Datart) authenticates the end user and forwards
identity over trusted internal headers. The provider maps
``orgId`` → ``tenant_id`` (the first-class tenant boundary),
``userId`` → ``user_id`` (session scope), ``agentId`` → ``sub_agent_name``
(knowledge-base read boundary), and assembles a ``policy_context`` consumed
by the gienbi-policy plugin and the Cube adapter (``cube_org_id`` follows
the chat2agent/Java ``metaOrgId = orgId + "A"`` convention).
"""

from unittest.mock import MagicMock

import pytest

from datus.api.auth.context import AppContext
from datus.api.auth.gienbi_provider import GienBIAuthProvider
from datus.utils.exceptions import DatusException


def _make_request(headers: dict | None = None) -> MagicMock:
    request = MagicMock()
    request.headers = headers or {}
    return request


FULL_HEADERS = {
    "X-GienBI-OrgId": "org-42",
    "X-GienBI-UserId": "alice",
    "X-GienBI-AgentId": "hr-bot",
    "X-GienBI-CubeToken": "jwt-from-java",
}


@pytest.mark.asyncio
class TestGienBIAuthProviderAuthenticate:
    async def test_full_headers_map_to_tenant_user_and_subagent(self):
        ctx = await GienBIAuthProvider().authenticate(_make_request(FULL_HEADERS))
        assert isinstance(ctx, AppContext)
        assert ctx.tenant_id == "org-42"
        assert ctx.user_id == "alice"
        assert ctx.sub_agent_name == "hr-bot"

    async def test_policy_context_carries_gienbi_identity_and_cube_org(self):
        ctx = await GienBIAuthProvider().authenticate(_make_request(FULL_HEADERS))
        assert ctx.policy_context["gienbi_org_id"] == "org-42"
        assert ctx.policy_context["gienbi_user_id"] == "alice"
        assert ctx.policy_context["gienbi_agent_id"] == "hr-bot"
        assert ctx.policy_context["cube_token"] == "jwt-from-java"
        # chat2agent/Java convention: metaOrgId = orgId + "A"
        assert ctx.policy_context["cube_org_id"] == "org-42A"

    async def test_no_headers_single_tenant_mode_is_anonymous(self):
        ctx = await GienBIAuthProvider(multi_tenant=False).authenticate(_make_request({}))
        assert ctx.tenant_id is None
        assert ctx.user_id is None
        assert ctx.sub_agent_name is None
        assert ctx.policy_context == {}

    async def test_missing_headers_multi_tenant_mode_fails_closed(self):
        provider = GienBIAuthProvider(multi_tenant=True)
        with pytest.raises(DatusException):
            await provider.authenticate(_make_request({}))

    async def test_org_without_user_multi_tenant_mode_fails_closed(self):
        provider = GienBIAuthProvider(multi_tenant=True)
        with pytest.raises(DatusException):
            await provider.authenticate(_make_request({"X-GienBI-OrgId": "org-42"}))

    async def test_whitespace_only_headers_treated_as_missing(self):
        provider = GienBIAuthProvider(multi_tenant=True)
        with pytest.raises(DatusException):
            await provider.authenticate(
                _make_request({"X-GienBI-OrgId": "   ", "X-GienBI-UserId": "  "})
            )

    async def test_invalid_org_characters_rejected(self):
        provider = GienBIAuthProvider()
        with pytest.raises(DatusException):
            await provider.authenticate(
                _make_request({"X-GienBI-OrgId": "org/42", "X-GienBI-UserId": "alice"})
            )

    async def test_agent_and_cube_token_are_optional(self):
        ctx = await GienBIAuthProvider().authenticate(
            _make_request({"X-GienBI-OrgId": "org-42", "X-GienBI-UserId": "bob"})
        )
        assert ctx.sub_agent_name is None
        assert "cube_token" not in ctx.policy_context
        assert ctx.policy_context["cube_org_id"] == "org-42A"


def test_provider_satisfies_auth_provider_protocol():
    from datus.api.auth.provider import AuthProvider

    assert isinstance(GienBIAuthProvider(), AuthProvider)


@pytest.mark.asyncio
class TestReservedDefaultOrg:
    async def test_org_named_default_is_rejected(self):
        """'default' is the reserved single-tenant namespace — an org with this
        literal name must not silently share legacy rows."""
        provider = GienBIAuthProvider()
        with pytest.raises(DatusException):
            await provider.authenticate(
                _make_request({"X-GienBI-OrgId": "default", "X-GienBI-UserId": "alice"})
            )
