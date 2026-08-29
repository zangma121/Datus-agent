# GienBI Policy Plugin

The `gienbi_policy` plugin connects Datus to the GienBI platform's permission
model and multi-tenant identity. It ships two cooperating pieces:

| Piece | What it does |
|---|---|
| `GienBIAuthProvider` (auth) | Maps trusted gateway headers onto the request context: tenant, user, agent scope, and an optional Cube JWT passthrough. |
| `GienbiPolicyRuntime` (policy) | Enforces the GienBI permission model on every agent read: metric-level VIEW gating, row-level filters, and column masking. |

## Identity headers

`GienBIAuthProvider` reads the request identity from gateway-injected
headers and never trusts a client-supplied tenant blindly:

| Header | Maps to | Purpose |
|---|---|---|
| `X-GienBI-OrgId` | `tenant_id` | Tenant boundary (KB storage, session dirs, Cube `cubeOrgId`) |
| `X-GienBI-UserId` | `user_id` | Session scope and permission subject |
| `X-GienBI-AgentId` | `sub_agent_name` | KB read boundary (optional) |
| `X-GienBI-CubeToken` | Cube JWT | Passthrough token for the Cube engine (optional) |

The literal org id `default` is rejected — it is reserved for the
single-tenant fallback and allowing it would blur tenant boundaries.

## Enabling multi-tenancy

```yaml
api:
  auth_provider:
    class: datus.api.auth.gienbi_provider:GienBIAuthProvider
    kwargs:
      multi_tenant: true
  multi_tenant: true          # deployment-level switch
```

With `multi_tenant: true` (either level), requests missing org/user identity
are rejected fail-closed instead of degrading to anonymous, and providers
that cannot carry tenant identity are rejected at load time.

Multi-tenancy keys everything below the request:

- knowledge-base storage rows carry a `tenant_id` column and
  `{tenant}:{datasource}:{row}`-prefixed storage keys;
- session directories layer as `{session_dir}/{tenant}/{scope}/`;
- the Cube engine signs per-tenant JWTs with `cubeOrgId = {tenant}A`
  unless a `X-GienBI-CubeToken` passthrough is present.

## Policy enforcement

The policy runtime hooks four points in the agent's read path:

| Hook | Enforcement |
|---|---|
| `validate_context` | Rejects requests without usable GienBI org/user identity (multi-tenant mode). |
| `before_metric_read` | Hides metrics the caller has no VIEW permission on — listing and querying both. |
| `before_sql_read` | Injects row-level filters into SQL WHERE clauses; on the Cube engine the same rules compile into Cube `filters` (dimensions) and `havingFilters` (measures). |
| `after_read_result` | Masks restricted columns in returned rows. |

Permission subjects are the union of the user's USER, ROLE, and DEPT
entries in the GienBI permission tables. The runtime reads those tables
over MySQL and caches per-user for `permission_cache_ttl_seconds`
(default 60s).

## Configuration

```yaml
agent:
  plugins:
    gienbi_policy:
      profiles:
        default:
          mysql_host: mysql.internal
          mysql_port: 3306
          mysql_user: datus_reader
          mysql_password: ${GIENBI_MYSQL_PASSWORD}
          mysql_database: gienbi
          permission_cache_ttl_seconds: 60
          multi_tenant: true
```

Credentials belong in environment-variable references, not in the file.
Activate the plugin per project with `plugins: {gienbi_policy: {enabled:
true}}` in `./.datus/config.yml` (see [Plugins](introduction.md)).

## Current limitations

- The row-policy grammar covers the GienBI rule-tree subset (dimension
  value conditions); dimension-side row scoping (restricting which
  dimension values exist at all) is future work (B10 in the Cube plan).
- The multi-tenant Cube JWT path (`cubeOrgId`) and the permission matrix
  are unit-tested; end-to-end verification needs the real GienBI stack
  (B6/B7 in the Cube plan).
