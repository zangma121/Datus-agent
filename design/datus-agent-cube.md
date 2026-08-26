# datus-agent-cube 设计方案

日期：2026-08-25 ｜ 分支：`datus-agent-cube` ｜ 状态：设计定稿（grilling 访谈 10/10 题已确认）

目标：在 Datus 上补齐多租户地基（一等 `tenant_id`），接入 Cube.js 语义层（GienBI
现有语义层），提供 `engine=metricflow/cube` 切换，并把 GienBI 的指标/列/行三级权限
做成策略插件。

---

## 0. 代码事实基础（已核实）

| 事实 | 位置 | 对设计的影响 |
|---|---|---|
| 语义层引擎开关已存在：`agent.services.semantic_layer` 命名条目 + 三级解析（显式 `adapter_type` → 项目 pin `active_semantic` → `default: true`） | `datus/configuration/agent_config.py:2134` `resolve_semantic_adapter()` | 不需要新增 `engine:` 配置键，`engine=metricflow/cube` 就是 semantic_layer 条目选择 |
| 适配器经 `datus.semantic_adapters` entry point 自动注册；README 预留 `datus_semantic_cube` | `datus/tools/semantic_tools/README.md`、`registry.py` | Cube 适配器按既有模式实现即可 |
| PolicyRuntime 四钩子：`validate_context` / `before_sql_read` / `before_metric_read` / `after_read_result` | `datus/tools/policy_runtime.py:64-98` | 正好对应 GienBI 租户校验/行权限/指标权限/列屏蔽 |
| `before_sql_read`、`after_read_result` 已在 SQL 执行路径接线；**`before_metric_read` 已声明、无调用点** | `datus/tools/func_tool/database.py:2137,2172` | 指标级权限需要在 SemanticTools 路径补一处接线（小改、上游可合并） |
| `AppContext(user_id, project_id, policy_context, sub_agent_name)`；session scope=user_id；KB 行隔离=project 内 `datasource_id`；DatusService 缓存按 project 键控 | `datus/api/auth/context.py`、`datus/storage/datasource_scope.py`、`datus/api/services/datus_service_cache.py` | 本方案在其上新增一等 `tenant_id`（见 D1/D2） |
| SaaS 模式已有约定：每租户克隆 `AgentConfig`（不可变、`config_mutable=False`） | `datus/configuration/agent_config.py:1375-1400` | 租户差异走 policy_context / 配置克隆，不改全局单例 |
| chat2agent 的 Cube JWT：HS256，claim `cubeOrgId = orgId + "A"`（env `CUBE_ORG_ID` 可覆盖），30 分钟；优先复用 Java 下发的 cubeToken | `chat2agent/api/core/skills/query_execute.py:72-96` | 适配器照搬同一套 token 协议，与 Java 后端互通 |
| GienBI 权限表：`user_resource_permission_flat`（指标 VIEW 位）、`rel_subject_columns`（列禁止）、`semantic_model` 行权限脚本（AND/OR，deny-by-default，ORG_OWNER 旁路） | chat2agent `resource_permission.py`（1,168 行） | 权限插件直读同一 MySQL 库，逻辑可移植 |

---

## 1. 决策记录（grilling 访谈确认，10/10）

| # | 决策点 | 结论（访谈确认） | 备选（未采纳原因） |
|---|---|---|---|
| D1 | 租户身份建模 | **新增一等 `tenant_id`**：贯穿 AppContext、存储、缓存、会话 | org→project_id 复用（零 schema 改动，但租户语义隐式） |
| D2 | 层级与键控 | **tenant > project 两级**：存储 storage_key、session 目录、DatusService 缓存键全部改为 (tenant_id, project_id) 两级 | tenant 替代 project（将来一租户多项目要二次改造） |
| D3 | 身份来源 | **`GienBIAuthProvider` + 内网信任**：从 Java 网关转发头解析 orgId/userId/agentId/cubeToken → `AppContext.tenant_id` + `policy_context`；多租户模式 fail-closed（缺失即 400） | 网关 JWT 验签（更硬但多一套密钥管理）；扩展现有 header provider（校验逻辑分散） |
| D4 | 存储隔离形态 | **逻辑隔离**：共享库 + tenant 列/前缀 + WHERE 过滤；session 目录插 `{tenant}/` 层；缓存键 (tenant, project) | 物理隔离每租户独立库（句柄膨胀、运维面大）；RDB 行过滤+向量库分目录（两套语义并存） |
| D5 | Cube 租户协议 | **沿用现有协议**：优先透传 Java cubeToken，缺失时自签 HS256（`cubeOrgId={tenant}A`，30min，secret 走环境变量） | 永远自签（需严格同步 claim 格式）；Cube 多 orchestrator 改造（超范围） |
| D6 | 适配器位置 | **树内包 `datus_semantic_cube/`**（本分支），entry point 注册，验证后可拆独立仓库 | 独立适配器仓库（跨仓迭代慢）；datus 插件形态（非标准注册路径） |
| D7 | 检索策略 | **storage-first**：`bootstrap-kb --from_adapter cube` 同步 `/meta` 进 LanceDB/FTS（含别名展开），`query_metrics` 实时走 `/load` | 全实时（无向量检索）；同步+定时增量（留作 M3 后增强） |
| D8 | engine 开关 | **复用 `semantic_layer` 条目**：`metricflow: {}` + `cube: {...}`，`default: true` 或项目级 `semantic: cube` 切换；无新配置键。CLI 入口：已有 `/services` TUI + 新增薄别名 `/engine`（见 4.1） | 新增顶层 `engine:` 键（双套语义）；请求级切换（口径与缓存复杂度失控） |
| D9 | 权限数据源 | **直读 GienBI MySQL + 60s TTL 缓存**（按 user 键控），与 chat2agent 同一事实源 | Java 权限 API（多一跳+故障面）；同步本地权限库（双源漂移，安全属性不可接受） |
| D10 | 行权限实施点 | **插件统一算过滤条件 + 按引擎分发**：cube→注入 MQL filters；metricflow→`before_sql_read` sqlglot 改写，无法表达即拒绝 | Cube securityContext（双份配置必漂移）；拒绝式（功能损失大） |

---

## 2. 多租户地基（M1，本方案最大的改造面）

### 2.1 身份模型

```
Java 网关(Datart) ──转发头──▶ GienBIAuthProvider ──▶ AppContext
                                                     ├─ tenant_id    = orgId        (新增字段)
                                                     ├─ user_id      = userId
                                                     ├─ sub_agent_name = agentId     (可选，KB 读取边界)
                                                     └─ policy_context = {
                                                          gienbi_org_id, gienbi_user_id,
                                                          gienbi_agent_id, cube_token(可选),
                                                          cube_org_id = orgId+"A" }
```

- `AppContext` 新增 `tenant_id: Optional[str]`；`None` = 单租户兼容模式（CLI/本地
  使用不受影响，落默认租户 `default`）。多租户部署开关 `agent.multi_tenant: true`
  时 Provider fail-closed：tenant/user 缺失即 400。
- datus 不做用户鉴权（内网信任 Java 转发），只做存在性与格式校验——与 chat2agent
  现状一致；将来升级 JWT 验签只改 Provider 一处。

### 2.2 两级键控改造清单（tenant > project）

| 位置 | 现状 | 改为 |
|---|---|---|
| KB 行隔离（`datus/storage/datasource_scope.py`） | `storage_key = {datasource_id}:{row_id}`，表内 `datasource_id` 列 | `storage_key = {tenant_id}:{datasource_id}:{row_id}`，表加 `tenant_id` 列，`tenant_condition()` 并入 `datasource_condition()` |
| session 目录（`datus/models/session_manager.py`） | `{session_dir}/{scope}/`（scope=user_id） | `{session_dir}/{tenant_id}/{scope}/` |
| DatusService 缓存（`datus/api/services/datus_service_cache.py`） | LRU 按 project_id | LRU 按 (tenant_id, project_id) 二元组 |
| 语义层/agent 配置解析 | project 级 `.datus/config.yml` | 同一 project 名在不同 tenant 下各自解析（配置目录加 tenant 段） |

- 存量数据迁移：默认租户回填（`tenant_id = 'default'`），单租户部署行为不变。
- **改造代价（如实记录）**：`datasource_scope.py`、`session_manager.py`、
  `datus_service_cache.py` 是上游文件，此路线的合并冲突面显著大于"复用 project_id"
  路线——这是 D1/D2 决策接受的代价，换取的是显式租户语义与未来一租户多项目能力。

### 2.3 隔离测试（移植 chat2agent `test_tenant_isolation.py` 形态）

1. 跨租户 KB 检索不可见（同 datasource 名不同 tenant）。
2. 跨租户会话/缓存不串（并发问答验证）。
3. 多租户模式下 tenant/user 缺失 → 400。
4. 单租户兼容模式（tenant_id=None）行为与上游一致。

## 3. `datus_semantic_cube` 适配器（M2，树内包）

接口映射（`BaseSemanticAdapter` → Cube REST）：

| BaseSemanticAdapter 方法 | Cube API | 说明 |
|---|---|---|
| `list_metrics(path, limit, offset)` | `GET /cubejs-api/v1/meta` | measures→`MetricDefinition`；path=Cube 名（数据集）；分页由 registry 的 `metric_catalog_page_size/max_pages` 约束 |
| `get_dimensions(metric_name, path)` | `/meta`（按 measure 反查 cube） | 返回该 cube 的 dimensions + members |
| `query_metrics(...)` | `POST /cubejs-api/v1/load` | measures/dimensions/timeDimensions/filters/limit/order → `QueryResult`；行数上限对齐 datus sql_guard 语义 |
| `query_metrics(dry_run=True)` | `POST /cubejs-api/v1/sql` | 返回编译 SQL，满足 datus 的 explain/展示路径 |
| `validate_semantic()` | `/meta` 可达性 | 200 即 valid；后续可加 pre-aggregation 状态检查 |
| `get/list_semantic_models` | `/meta` cubes | cubes→语义模型名列表 |
| `sync_to_storage()` | 走 `SemanticStorageManager.sync_from_adapter` | bootstrap-kb 落 LanceDB/FTS（storage-first） |

租户与认证（D5）：

- **Token 优先级**：`policy_context.cube_token`（Java 下发，透传）→ 自签 HS256
  （claim `cubeOrgId={tenant}A`，`exp` 30min，secret 只从环境变量读，禁止明文落配置）。
- **每请求租户上下文**：适配器实例不缓存跨租户状态；httpx AsyncClient 连接池复用；
  租户标识从 `AppContext.tenant_id`/`policy_context` 注入，同步进 KB 的记录打上
  tenant 维度（对齐 2.2 的两级键控）。
- **权限错误映射**：Cube 403/权限类错误 → `POLICY_REFUSED`（复用上游 read refusal
  独立错误码语义），带插件 denial 说明，不落入通用查询错误。

配置（agent.yml，D8）：

```yaml
services:
  semantic_layer:
    metricflow: {}          # 现状保留，engine=metricflow
    cube:                   # engine=cube
      default: true
      api_url: ${CUBEJS_API_URL}
      api_secret: ${CUBEJS_API_SECRET}   # 仅自签 token 用
      timeout: 60
      timezone: Asia/Shanghai
      metric_catalog_page_size: 5000
```

项目级切换：`.datus/config.yml` 里 `semantic: cube`（已有机制，无新键）。

## 4. engine 切换语义（M3）

- metricflow 引擎 = 现有 datus 全流程（OSI/Dosi、语义建模 Agent、YAML 同步）。
- cube 引擎 = 检索与执行走 Cube；`list_metrics/get_dimensions/query_metrics/
  search_metrics` 及 `metric_to_sql`/`ask_metrics` 工作流自动切到 Cube，因为它们
  都消费 `SemanticTools`/registry。

### 4.1 CLI 中的 engine 设置

CLI 侧切换机制**已经存在**，M3 只做验证 + 一个易用性别名：

1. **已有**：`/services` 斜杠命令（`datus/cli/slash_registry.py:98`）打开
   `ServiceConfigApp` TUI，其中 `semantic_layer` 分组支持
   - "set global default"：写 `agent.services.semantic_layer.<name>.default: true`
     （`service_commands.py:286`）；
   - "set project default"：调 `AgentConfig.set_active_semantic()` 持久化到
     `.datus/config.yml` 的 `semantic:` pin（`service_commands.py:316`）；
   - probe/test：对 cube 条目即验证 `/meta` 可达性。
   M3 验收项：cube 条目在 `/services` TUI 中可选中、可设默认、probe 通过。
2. **新增（薄别名）**：`/engine` 斜杠命令，用使用者的词汇直达同一套 setter：
   - `/engine`：显示当前引擎（resolved adapter）+ 可用引擎列表（来自
     `semantic_layer_configs` 键）；
   - `/engine cube` / `/engine metricflow`：项目级切换（委托 `set_active_semantic`）；
   - `/engine --global cube`：设全局 `default: true`（委托现有 global-default 动作）。
   实现为 `slash_registry` 里的一个新 `SlashSpec` + 转发函数，**零新机制**；
   未配置目标引擎时按 `resolve_semantic_adapter()` 现有报错提示可用条目。
3. 启动参数（可选增强）：`datus --semantic cube`（一次性覆盖，不落盘）与
   `datus -p --semantic cube`，便于脚本/CI 中切换引擎跑 benchmark——直接复用
   `SemanticTools(adapter_type=...)` 显式参数路径。

### 4.2 降级面与同步

- **明确降级面**（写进文档与冒烟清单）：OSI 语义建模/发布类工具
  （`gen_semantic_model`、`publish_metrics` 等，`is_osi_semantic_adapter` 门控）在
  cube 引擎下不可用——语义建模权在 GienBI Java 侧；`attribution_analyze` 依赖
  metricflow 编译，cube 引擎下降级为 SQL 归因或禁用（M5 用数据定）。
- bootstrap：`datus-agent bootstrap-kb --datasource <ds> --components metrics,
  semantic_model --from_adapter cube --kb-update-strategy overwrite`。
- 指标别名：同步时按 chat2agent `ingest_with_aliases` 模式展开（主记录+别名记录
  共享 element_id），保证"销售额/营收"两类问法都能召回。

## 5. `gienbi-policy` 策略插件（M4）

```
manifest: datus-plugin.yml（policy_runtime 工厂）
    │
    ├─ validate_context    多租户模式下要求 gienbi_org_id/gienbi_user_id；ORG_OWNER 旁路标记
    ├─ before_metric_read  查 user_resource_permission_flat（VIEW 位）过滤指标；
    │                      denial 记入结果元数据（沿用 permission_filtered_metrics 语义）
    ├─ before_sql_read     engine=metricflow 时：行权限脚本→sqlglot 改写（AND/OR 组合，
    │                      无法表达即拒绝，deny-by-default）
    └─ after_read_result   rel_subject_columns 禁止列 → 脱敏/剔除 + masked 警告
```

- **行权限统一计算、按引擎分发**（D10）：插件从 `semantic_model` 行权限脚本算出
  过滤条件（移植 chat2agent `get_row_scope()`：`permission_operator` AND/OR 组合、
  无法转换默认拒绝）；engine=cube → 过滤条件经 policy_context 传给适配器，组装进
  Cube query filters；engine=metricflow → `before_sql_read` sqlglot 改写。
- 权限读取：直读 GienBI MySQL（D9），进程内 TTL 缓存 60s、按 user 键控，
  ORG_OWNER 直接放行。
- 接线改动：`datus/tools/func_tool/semantic_tools.py` 的 list/search/query 路径
  调 `policy_runtime.before_metric_read`（纯增量，上游可提 PR）。

## 6. 实施切分

| 里程碑 | 内容 | 验收 |
|---|---|---|
| M0 | 基线：metricflow 引擎行为快照测试（现有 semantic_layer 用例跑通留档） | 快照绿 |
| M1a | 身份层：AppContext.tenant_id + GienBIAuthProvider + fail-closed 校验 + 单租户兼容模式 | 头缺失 400；默认租户兼容 |
| M1b | 键控层：datasource_scope/storage_key/session 目录/服务缓存两极化 + 存量默认租户迁移 | 隔离测试 4 项全绿 |
| M2 | `datus_semantic_cube` 包：meta/load/sql + JWT + mock 单测 | mock 单测绿 |
| M3 | engine 切换 + `/engine` CLI 别名 + `/services` TUI 验证 + bootstrap-kb 同步 + 工作流冒烟（metric_to_sql/ask_metrics on cube） | `/engine cube` 生效；cube 条目在 `/services` 可设默认、probe 通过；真实 Cube 环境问答成功 |
| M4 | gienbi-policy 插件 + `before_metric_read` 接线 + 行级注入 + 列屏蔽 | 权限矩阵 E2E（有/无权限/Owner/禁列） |
| M5 | 评估：semantic_layer benchmark 在 cube 引擎重跑；权限矩阵回归；延迟对比 chat2agent；attribution 降级决策 | 报告出数 |
| M6（可选） | 适配器拆包至 `datus-semantic-adapter` 仓库；同步+定时增量（D7 增强） | - |

## 7. 风险与开放问题

1. **上游合并面（最大的结构性风险）**：D1/D2 的一等 tenant_id 要动
   `datasource_scope.py`、`session_manager.py`、`datus_service_cache.py` 三个上游
   核心文件——与上游 datus 的后续合并冲突面显著增大。缓解：改动保持"加字段+默认
   值兼容"形态（tenant_id=None 即旧行为），并尽量把两极化逻辑收敛在独立函数里。
2. **`before_metric_read` 接线**是 semantic_tools 的上游小改——优先给上游提 PR，
   分支内先垫。
3. **Cube `/meta` 大租户性能**：默认分页 5000×200=1M 上限；银行级租户指标量需实测，
   必要时走增量同步（`updated_at`）。
4. **归因分析降级**：cube 引擎下 `attribution_analyze` 走 SQL 归因还是禁用，M5 定。
5. **术语层缺口**：datus 无 `agent_terminology` 对应物；短期靠别名展开进 KB，
   长期评估 subject_tree/文档 KB 承载。
6. **双引擎并存**：同一 (tenant, project) 只能一个 active 引擎——
   `resolve_semantic_adapter` 已保证；文档写清切换是项目级不是请求级。
7. **Cube token 信任边界**：透传 Java token 时租户正确性由 Java 保证；自签路径
   secret 只进环境变量，禁止落配置文件明文（吸取 chat2agent 文档泄密教训）。
