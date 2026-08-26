"""Spec for two-level (tenant > project/datasource) storage keying — M1b T1.5.

Compatibility rule: the default tenant keeps the legacy storage_key format
``{datasource}:{row_id}`` and adds no filter, so existing data and queries
are unchanged. Non-default tenants get a ``{tenant}:{datasource}:{row_id}``
key and a ``storage_key LIKE '{tenant}:{datasource}:%'`` read filter, which
isolates their rows without a schema migration.
"""

from types import SimpleNamespace

import pytest

from datus.storage.datasource_scope import (
    add_datasource_scope_to_rows,
    build_storage_key,
    datasource_condition,
    resolve_tenant_id,
    tenant_condition,
)


class TestResolveTenantId:
    def test_unset_everywhere_resolves_default(self):
        assert resolve_tenant_id(SimpleNamespace()) == "default"

    def test_explicit_argument_wins(self):
        assert resolve_tenant_id(SimpleNamespace(tenant_id="cfg-org"), "arg-org") == "arg-org"

    def test_config_attribute_used_when_argument_missing(self):
        assert resolve_tenant_id(SimpleNamespace(tenant_id="cfg-org")) == "cfg-org"

    def test_blank_values_fall_back_to_default(self):
        assert resolve_tenant_id(SimpleNamespace(tenant_id="   "), "  ") == "default"


class TestBuildStorageKey:
    def test_default_tenant_keeps_legacy_format(self):
        assert build_storage_key("california_schools", "r1") == "california_schools:r1"
        assert build_storage_key("california_schools", "r1", tenant_id="default") == "california_schools:r1"

    def test_tenant_prefixes_the_key(self):
        assert build_storage_key("california_schools", "r1", tenant_id="org-42") == "org-42:california_schools:r1"


class TestTenantCondition:
    def test_default_tenant_has_no_condition(self):
        assert tenant_condition("default") is None
        assert tenant_condition(None) is None

    def test_tenant_condition_matches_key_prefix(self):
        node = tenant_condition("org-42")
        assert node is not None
        assert node.field == "storage_key"
        assert node.value == "org-42:%"

    def test_datasource_condition_default_tenant_unchanged(self):
        plain = datasource_condition("ds1")
        scoped = datasource_condition("ds1", tenant_id="default")
        assert plain.field == scoped.field == "datasource_id"
        assert plain.value == scoped.value == "ds1"

    def test_datasource_condition_with_tenant_scopes_by_prefix(self):
        scoped = datasource_condition("ds1", tenant_id="org-42")
        rendered = str(scoped)
        assert "datasource_id" in rendered and "storage_key" in rendered


class TestAddDatasourceScopeToRows:
    def test_default_tenant_rows_keep_legacy_keys(self):
        rows = add_datasource_scope_to_rows([{"id": "r1"}], "ds1")
        assert rows[0]["datasource_id"] == "ds1"
        assert rows[0]["storage_key"] == "ds1:r1"

    def test_tenant_rows_carry_prefixed_keys(self):
        rows = add_datasource_scope_to_rows([{"id": "r1"}], "ds1", tenant_id="org-42")
        assert rows[0]["datasource_id"] == "ds1"
        assert rows[0]["storage_key"] == "org-42:ds1:r1"


class TestTenantIdValidation:
    def test_invalid_tenant_characters_rejected(self):
        from datus.utils.exceptions import DatusException

        with pytest.raises(DatusException):
            build_storage_key("ds1", "r1", tenant_id="org/42")

    def test_reserved_default_prefix_rejected(self):
        from datus.utils.exceptions import DatusException

        with pytest.raises(DatusException):
            build_storage_key("ds1", "r1", tenant_id="default:ds1")
