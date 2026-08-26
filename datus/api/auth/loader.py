"""Dynamic AuthProvider loader.

Resolves an ``AuthProvider`` implementation declared in ``agent.yml`` under the
``api.auth_provider`` section. Falls back to :class:`HeaderContextProvider`
when no provider is configured.
"""

import importlib
from typing import Any, Dict, Optional

from datus.api.auth.header_context_provider import HeaderContextProvider
from datus.api.auth.provider import AuthProvider
from datus.utils.exceptions import DatusException, ErrorCode
from datus.utils.loggings import get_logger

logger = get_logger(__name__)


def load_auth_provider(api_config: Optional[Dict[str, Any]], datasource: str) -> AuthProvider:
    """Load an AuthProvider instance from the ``api.auth_provider`` config section.

    Args:
        api_config: The ``api`` section dict from agent.yml (may be ``None``).
        datasource: Default datasource retained for the loader contract.

    Returns:
        An ``AuthProvider`` instance — either the custom one declared in config
        or the default :class:`HeaderContextProvider`.
    """
    spec = (api_config or {}).get("auth_provider") or {}
    class_path = spec.get("class")
    if not class_path:
        provider: AuthProvider = HeaderContextProvider()
        if (api_config or {}).get("multi_tenant"):
            _escalate_multi_tenant(provider)
        return provider

    normalized = class_path.replace(":", ".")
    module_name, _, class_name = normalized.rpartition(".")
    if not module_name or not class_name:
        raise DatusException(
            ErrorCode.COMMON_FIELD_INVALID,
            message=f"Invalid auth_provider class path: {class_path!r}. Expected 'module.Class' or 'module:Class'.",
        )

    try:
        module = importlib.import_module(module_name)
    except ImportError as e:
        raise DatusException(
            ErrorCode.COMMON_FIELD_INVALID,
            message=f"Failed to import auth_provider module {module_name!r}: {e}",
        ) from e

    try:
        cls = getattr(module, class_name)
    except AttributeError as e:
        raise DatusException(
            ErrorCode.COMMON_FIELD_INVALID,
            message=f"Auth provider class {class_name!r} not found in module {module_name!r}",
        ) from e

    kwargs = spec.get("kwargs") or {}
    try:
        instance = cls(**kwargs)
    except Exception as e:
        raise DatusException(
            ErrorCode.COMMON_FIELD_INVALID,
            message=f"Failed to instantiate auth_provider {class_path!r}: {e}",
        ) from e

    if not isinstance(instance, AuthProvider):
        raise DatusException(
            ErrorCode.COMMON_FIELD_INVALID,
            message=f"{class_path} does not implement the AuthProvider protocol",
        )

    if (api_config or {}).get("multi_tenant"):
        instance = _escalate_multi_tenant(instance)

    logger.info(f"Loaded custom AuthProvider: {class_path}")
    return instance


def _escalate_multi_tenant(provider: AuthProvider) -> AuthProvider:
    """Enforce the deployment-level ``api.multi_tenant`` switch.

    A multi-tenant deployment must fail closed on missing identity. Providers
    that support the switch get it forced on (so omitting the per-provider
    kwarg cannot silently degrade to anonymous contexts); providers that
    cannot carry tenant identity are rejected at startup instead of being
    discovered as fail-open on the first anonymous request.
    """
    multi_tenant_getter = getattr(provider, "multi_tenant", None)
    if multi_tenant_getter is None:
        raise DatusException(
            ErrorCode.COMMON_CONFIG_ERROR,
            message=(
                "api.multi_tenant is enabled but auth provider "
                f"{type(provider).__name__} cannot carry tenant identity; "
                "configure a tenant-aware provider such as GienBIAuthProvider."
            ),
        )
    provider.multi_tenant = True
    return provider
