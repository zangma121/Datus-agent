# Cube 语义适配器

Cube 语义适配器把 Datus 的语义查询路由到 [Cube.js](https://cube.dev)
部署。OSI YAML 始终是语义模型的**唯一模型源**；Cube 的 `.js` 模型文件是从该源
（或从在线 schema 探查）**生成**的，不需要手工维护。

适用场景：希望 Datus 的 agentic 查询循环经由 Cube 编译指标——例如复用既有
Cube 部署的预聚合、访问策略，或多租户 `cubeOrgId` 安全上下文。

## 配置

在 `agent.services.semantic_layer` 下启用 cube 引擎：

```yaml
agent:
  services:
    semantic_layer:
      cube:
        datasource: bird_sqlite        # 本语义层服务的 Datus 数据源
        api_url: http://localhost:4000/cubejs-api/v1
        api_secret_env: CUBEJS_API_SECRET
        timeout: 60
        timezone: UTC
```

API secret **只按环境变量名引用**——绝不要把密钥明文写进 `agent.yml`。该变量的值必须与
Cube 部署启动时使用的值一致：

```bash
export CUBEJS_API_SECRET=<与 cube 容器相同的值>
```

运行期用 `/engine cube`（项目默认）或 `/engine --global cube` 切换引擎。
metricflow 系引擎走既有流程；`cube` 走本适配器。不带参数执行 `/engine`
可列出已配置的引擎。

> 本机提示：如果 shell 设置了 `HTTP_PROXY`/`ALL_PROXY`，查询本地 Cube 前请导出
> `NO_PROXY='*'`（或把 `localhost` 加进去），否则 REST 请求会被代理拦截并以 502 失败。

## 生成 Cube 模型 —— 同一命令，双源用法

`generate-cube-models` 生成 Cube 部署所需的 `.js` 模型文件。同一条命令支持两种
输入源，按需选择：

> 该子命令通过 `datus-agent` 入口（或 `python -m datus.main`）执行，
> `datus` REPL 入口不认识它。

| | 默认（schema + 采样） | `--from-osi`（转换） |
|---|---|---|
| 输入 | 在线数据源 schema + 列值采样 | OSI YAML 目录 |
| 方式 | LLM 编写成员与描述 | 确定性映射，无 LLM |
| 依赖 DB / LLM / secret | 需要 / 需要 / 不需要 | 都不需要 |
| 适用 | 尚无 OSI 模型时的冷启动 | OSI YAML 是唯一模型源（推荐，CI 安全） |

### 源 1 —— schema + 采样值（LLM）

```bash
datus-agent generate-cube-models \
  --datasource bird_sqlite \
  --out ./cube_models/bird \
  --tables frpm,schools,satscores \
  --sample-rows 5 \
  --force
```

`--tables` 可省（留空 = 全部表）；`--force` 覆盖 `--out` 里的既有文件。生成器
对每列采样取值，由 LLM 产出成员名/类型/描述，并对产出的 JS 做 lint。

### 源 2 —— OSI YAML（确定性转换）

```bash
datus-agent generate-cube-models \
  --datasource bird_sqlite \
  --from-osi <OSI-YAML目录> \
  --out <输出目录> \
  --force
```

以本仓库的样例模型为例：

```bash
datus-agent generate-cube-models \
  --datasource bird_sqlite \
  --from-osi tests/data/semantic_models/bird_school \
  --out /tmp/cube_models/bird \
  --force
```

说明：

- `--from-osi` 接的是**目录**；目录下每个 `*.yml` / `*.yaml` 都会被转换
  （每个 data source 产出一份 `.js`）。
- `--datasource` 仍是 CLI 必填项，但在此模式下**不会被使用**——输入是 YAML，
  不是数据库。
- 运行结束会按模型打印 `status` + `lint` 的 JSON 摘要；可以把它当作 CI 门禁。
- 相同输入必然产出相同输出——可放心重复生成，也可在 code review 中直接 diff。

### 映射规则（OSI → Cube）

| OSI | Cube | 说明 |
|---|---|---|
| `measures[].agg` | `measure.type` | `SUM→sum`、`AVG/average→average`、`COUNT→count`、`COUNT_DISTINCT→count_distinct`、`MIN→min`、`MAX→max` |
| `measures[].expr` | `measure.sql` | 原样透传；**绝不**自己包一层 `SUM(...)`——`type: sum` 已负责聚合，嵌套会变成双重聚合 |
| 带操作符的 `expr`（如 `a / b` 比率） | **双发** | 聚合 `measure`（算总量）+ 行级 `<Name>PerRow` 维度（供按行排序/过滤） |
| 跨模型同名 `PRIMARY` identifier | `belongsTo` join | 字母序靠后的模型指向靠前的模型 |
| `type: TIME` 的维度 | 普通维度 | 时间粒度由 Cube 自有的时间维度机制负责 |
| `description` | `description` | 原样透传；为空时省略该字段（Cube 拒绝空字符串） |
| `sql_query` 源 | `sql` | 别名化的 SELECT 直接作为 cube 的 `sql` |

## 查询行为

- **纯维度（点查）查询是一等公民**：`metrics` 为空合法；适配器会省略 `measures`
  键而不是报错。
- 对比率成员排序时用它的 `PerRow` 维度，而不是聚合 measure。
- 成员级条件映射为 Cube `filters`；指标级条件映射为 `havingFilters`。
- 每个请求用 `CUBEJS_API_SECRET` 签名的 HS256 JWT 认证（30 分钟有效期）。
  多租户部署下，租户由 `cubeOrgId` claim 携带。
