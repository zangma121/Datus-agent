# Cube Semantic Adapter

The Cube semantic adapter routes Datus semantic queries to a [Cube.js](https://cube.dev)
deployment. OSI YAML remains the single source of truth for semantic models;
Cube `.js` model files are **generated** from that source (or from live schema
inspection) and never hand-maintained.

Use this adapter when you want Datus' agentic query loop to compile metrics
through Cube — for example to reuse an existing Cube deployment's pre-aggregations,
access policies, or multi-tenant `cubeOrgId` security context.

## Configuration

Enable the Cube engine under `agent.services.semantic_layer`:

```yaml
agent:
  services:
    semantic_layer:
      cube:
        datasource: bird_sqlite        # Datus datasource this layer serves
        api_url: http://localhost:4000/cubejs-api/v1
        api_secret_env: CUBEJS_API_SECRET
        timeout: 60
        timezone: UTC
```

The API secret is referenced **by environment-variable name only** — never
inline the secret in `agent.yml`. Point the variable at the same value your
Cube deployment was started with:

```bash
export CUBEJS_API_SECRET=<same value as the cube container>
```

Switch engines at runtime with `/engine cube` (project default) or
`/engine --global cube`. `metricflow`-family engines keep the existing
pipeline; `cube` goes through this adapter. Run `/engine` with no argument to
list configured engines.

> Localhost tip: if your shell sets `HTTP_PROXY`/`ALL_PROXY`, export
> `NO_PROXY='*'` (or add `localhost`) before querying a local Cube, or the
> REST calls will be routed into the proxy and fail with 502.

## Generating Cube Models — One Command, Two Sources

`generate-cube-models` produces the `.js` model files your Cube deployment
serves. The same command supports two input sources; pick per run:

> The subcommand runs through the `datus-agent` entry point (or
> `python -m datus.main`), not the `datus` REPL entry point.

| | Default (schema + samples) | `--from-osi` (transpile) |
|---|---|---|
| Input | live datasource schema + sampled column values | OSI YAML directory |
| How | LLM writes members + descriptions | deterministic mapping, no LLM |
| Needs DB / LLM / secret | yes / yes / no | no / no / no |
| Best for | bootstrap when no OSI models exist yet | OSI YAML is the source of truth (recommended, CI-safe) |

### Source 1 — schema + sampled values (LLM)

```bash
datus-agent generate-cube-models \
  --datasource bird_sqlite \
  --out ./cube_models/bird \
  --tables frpm,schools,satscores \
  --sample-rows 5 \
  --force
```

`--tables` is optional (empty = every table); `--force` overwrites existing
files in `--out`. The generator samples values per column, asks the LLM for
member names/types/descriptions, and lints the emitted JS.

### Source 2 — OSI YAML (deterministic transpile)

```bash
datus-agent generate-cube-models \
  --datasource bird_sqlite \
  --from-osi <osi-yaml-directory> \
  --out <output-directory> \
  --force
```

For example, against this repository's sample models:

```bash
datus-agent generate-cube-models \
  --datasource bird_sqlite \
  --from-osi tests/data/semantic_models/bird_school \
  --out /tmp/cube_models/bird \
  --force
```

Notes:

- `--from-osi` takes a **directory**; every `*.yml` / `*.yaml` in it is
  transpiled (one `.js` per data source).
- `--datasource` is still required by the CLI but is **not used** in this
  mode — the YAML is the input, not the database.
- The run prints a JSON summary of `status` + `lint` per model; treat it as
  the CI gate.
- Identical input always yields identical output — safe to regenerate, safe
  to diff in review.

### Mapping rules (OSI → Cube)

| OSI | Cube | Notes |
|---|---|---|
| `measures[].agg` | `measure.type` | `SUM→sum`, `AVG/average→average`, `COUNT→count`, `COUNT_DISTINCT→count_distinct`, `MIN→min`, `MAX→max` |
| `measures[].expr` | `measure.sql` | passed through verbatim; **never** wrap in `SUM(...)` yourself — `type: sum` already aggregates, nesting double-aggregates |
| measure `expr` with operators (e.g. `a / b` ratios) | **dual-emit** | aggregate `measure` (for totals) + row-level `<Name>PerRow` dimension (for per-row sorting/filtering) |
| same-name `PRIMARY` identifiers across models | `belongsTo` joins | the alphabetically-later model points at the earlier one |
| `dimensions` with `type: TIME` | plain dimension | Cube owns time granularity via its own time-dimension handling |
| `description` | `description` | passed through verbatim; omitted when empty (Cube rejects empty strings) |
| `sql_query` source | `sql` | the aliased SELECT is used as the cube's `sql` |

## Query Behavior

- **Dimension-only (point-lookup) queries are first-class**: an empty
  `metrics` list is valid; the adapter omits `measures` instead of failing.
- Sorting on a ratio member uses its `PerRow` dimension, not the aggregate
  measure.
- Member-level conditions become Cube `filters`; metric-level conditions
  become `havingFilters`.
- Each request is authenticated with an HS256 JWT signed from
  `CUBEJS_API_SECRET` (30-minute expiry). In multi-tenant deployments the
  tenant is carried in the `cubeOrgId` claim.
