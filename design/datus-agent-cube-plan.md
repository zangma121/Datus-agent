# datus-agent-cube 实施计划

日期：2026-08-26 ｜ 分支：`datus-agent-cube` ｜ 依据：`design/datus-agent-cube.md`（grilling 10/10 确认版）

任务分解规则：每个任务独立可提交、可验收（先跑验证再提交）；文件路径均为
`/Users/zm/Code/Datus-agent` 仓库内相对路径；`~` 指用户家目录。里程碑 M0–M6
对应设计文档第 6 节；任务编号 `T<里程碑>.<序号>`。

---

## 阶段总览

| 阶段 | 主题 | 任务数 | 依赖 |
|---|---|---|---|
| M0 | 基线快照 | 2 | 无 |
| M1a | 租户身份层 | 4 | M0 |
| M1b | 两级键控 | 5 | M1a |
| M2 | Cube 适配器包 | 6 | M0（与 M1 并行） |
| M3 | engine 切换 + CLI | 5 | M2 |
| M4 | gienbi-policy 插件 | 6 | M1a、M2（M3 建议先完成） |
| M5 | 评估 | 3 | M3、M4 |
| M6 | 拆包（可选） | — | 全部完成后 |

---

## M0 基线快照

### T0.1 metricflow 引擎行为快照
- **做**：跑通并留档现有语义层用例，作为后续所有改动的回归基线。
- **命令**：
  - `pytest unit_tests/tools/semantic_tools/ -x -q`（适配器注册/解析）
  - `pytest unit_tests/configuration/ -k semantic -q`
  - 真实环境（如有 metricflow 数据源）：`datus-agent -p "list metrics" ` 输出留档到
    `design/baseline_metricflow.md`
- **验收**：命令全绿或失败项已记录原因。

### T0.2 冒烟脚本固化
- **做**：把 `desc schools` 类最小问答（Qwen 模型，~20s）写进
  `scripts/smoke_chat.sh`（`datus -p` + 超时 + 关键字断言），M1–M4 每阶段收尾跑一次。
- **验收**：脚本在干净 shell 下一次通过。

---

## M1a 租户身份层（AppContext + Provider）

### T1.1 AppContext 增加 tenant_id
- **文件**：`datus/api/auth/context.py`
- **做**：`AppContext` 增加 `tenant_id: Optional[str] = None`，docstring 注明
  `None` = 单租户兼容模式（默认租户 `default`）；不改变现有字段语义。
- **验收**：`pytest unit_tests/api/ -q` 全绿（现有用例不感知新字段）。

### T1.2 GienBIAuthProvider
- **文件**：新建 `datus/api/auth/gienbi_provider.py`
- **做**：实现 `datus/api/auth/provider.py` 协议；从请求头解析
  `X-GienBI-OrgId / X-GienBI-UserId / X-GienBI-AgentId / X-GienBI-CubeToken`（头名
  集中为模块常量，便于网关侧对齐）；产出：
  - `AppContext(tenant_id=orgId, user_id=userId, sub_agent_name=agentId)`
  - `policy_context = {gienbi_org_id, gienbi_user_id, gienbi_agent_id,
    cube_token, cube_org_id: f"{orgId}A"}`
- **验收**：新增 `unit_tests/api/auth/test_gienbi_provider.py`：
  头齐全 → context 正确；头缺失 + 多租户开 → 拒绝；头缺失 + 多租户关 → 匿名。

### T1.3 multi_tenant 开关与 fail-closed
- **实现形态（评审后修订）**：不新增 AgentConfig 字段。部署级开关
  `api.multi_tenant: true`（agent.yml 的 api 段）由
  `datus/api/auth/loader.py` 的 `_escalate_multi_tenant()` 强制执行——
  已配置的 GienBI provider 未显式开 fail-closed 则自动升级为开；配了
  multi_tenant 却用无法携带租户身份的默认 Header provider 则启动即
  `COMMON_CONFIG_ERROR`。DatusException→400 的映射在 `deps.py:64-67`（存量）。
- **验收**：`unit_tests/api/test_loader.py`（开关升降级）+
  `unit_tests/api/test_deps.py`（400 映射/匿名兼容）✅ 已实现。

### T1.4 Provider 注册与配置
- **文件**：`datus/api/auth/loader.py`（或现有 provider 装载处）、
  `conf/agent.yml.example` 注释段
- **做**：`agent.auth.provider: gienbi` 选择该 provider；文档补一段配置示例。
- **验收**：API 启动日志显示 provider 生效；冒烟 `scripts/smoke_chat.sh` 仍绿
  （默认配置不受影响）。

---

## M1b 两级键控（tenant > project）

### T1.5 datasource_scope 两极化 ✅ 已实现（提交 cd8a7a75）
- **实现要点（比原计划更优）**：兼容优先设计——默认租户保持旧
  `{datasource}:{row_id}` 键与 `tenant_id=''` 列值，**零迁移**；非默认租户写
  `{tenant}:{datasource}:{row_id}` + `tenant_id` 列（经基类既有 ensure_columns
  机制自动加列），读路径 `tenant_column=True` 按列过滤（默认租户的
  `eq(tenant_id,'')` 同时排除外来租户行）；无列 store 走 LIKE 前缀兜底。
- **涉及**：`datasource_scope.py`（TENANT_ID_COLUMN/条件/键构建/校验）、
  `storage/base.py`（schema+迁移+默认值+删除路径）、`subject_tree/store.py`
  （基类 pop/盖章/6 处条件）、`metric/store.py`（4 处条件+MetricRAG resolve）、
  `storage/registry.py`（LRU 键加 tenant 段）。
- **测试**：`test_datasource_scope_tenant.py` + `test_tenant_isolation_unit.py`
  （跨租户不可见/默认租户不可见/旧格式保留）；存储套件 1940 全绿。

### T1.6 session 目录插层
- **文件**：`datus/models/session_manager.py`、
  `datus/agent/node/agentic_node.py`（session 路径拼接处，约 :360-390）
- **做**：`{session_dir}/{tenant_id}/{scope}/`；旧目录不迁移（历史会话留在
  default 外的历史位置或一次性脚本搬移，二选一在实现时定，倾向脚本搬移）。
- **验收**：两租户并发问答会话互不可见（列表/恢复各测一次）。

### T1.7 DatusService 缓存键改二元组 ✅ 已实现（提交 bc1fabd3）
- `get_or_create(project_id, factory, expected_fingerprint, tenant_id="")` 复合键
  `(tenant_id, project_id)`；`evict()` 同步带租户；`deps.py` 传入
  `ctx.tenant_id`。空租户 = 旧行为。测试：同项目异租户得不同实例、evict 按租户。

### T1.8 存量数据迁移脚本 ✅ 基本被兼容设计吸收
- 默认租户零迁移（旧键、`tenant_id=''`）；`tenant_id` 列由 ensure_columns 在
  首次打开表时自动补列回填 `''`。剩余工作：无（如后续发现无列 store 需要
  显式迁移再启用本任务）。

### T1.9 隔离测试套件（阶段验收）✅ 已实现（提交 c56a49ef + 评审修复 1c1624ce）
- `tests/integration/storage/test_tenant_isolation.py`：真实接线端到端
  （配置盖章 → MetricRAG → 注册表 → 行隔离）+ 会话目录分层 + fail-closed 链。
- **M1b 双轴评审已做**，关键修复：5 个未穿线的 KB store
  （reference_sql/reference_template/semantic_dataset/schema_metadata/kb_retrieval）
  全部穿线；kb_retrieval FTS 表加 tenant_id 列；保留字 "default" org 拒收。
- **遗留跟进项（评审发现，暂缓）**：
  1. 设计 2.2 第 4 行"同一 project 名在不同 tenant 下各自解析配置目录"未实现
     ——与每租户配置克隆深度耦合，排到 M3（engine 切换涉及配置解析时一并做）；
  2. SubjectTreeStore（主题树，非 embedding 表）未按租户隔离——泄的是业务
    分类结构而非行数据，排到 M4 之前评估必要性；
  3. kb_retrieval 的 facts/docs 表加了 tenant_id 列，存量表需重建
    （build-kb 即可），部署注意。

---

## M2 datus_semantic_cube 适配器包

### T2.1 包骨架与注册
- **文件**：新建 `datus_semantic_cube/{__init__.py, config.py}`、
  `pyproject.toml`（entry point `datus.semantic_adapters` → `cube`）
- **做**：`CubeConfig(SemanticAdapterConfig)`：`api_url`、`api_secret`(env)、
  `timeout`、`timezone`、分页参数；`register()` 注册
  `semantic_adapter_registry.register("cube", CubeAdapter, CubeConfig, "Cube")`。
- **参考**：`datus/tools/semantic_tools/README.md` Step 1–5。
- **验收**：`uv run pytest unit_tests/tools/semantic_tools/ -q` 后 registry 能列出
  cube 元数据（加一条注册冒烟用例）。

### T2.2 Cube HTTP 客户端与 JWT
- **文件**：新建 `datus_semantic_cube/client.py`、`token.py`
- **做**：httpx AsyncClient（连接池复用、timeout 可配）；
  `build_token(policy_context, api_secret)`：优先透传 `cube_token`，缺失自签
  HS256（claim `cubeOrgId`，`exp=+1800s`，secret 仅从环境变量读，禁止落配置）。
  协议对齐 chat2agent `query_execute.py:72-96`。
- **验收**：单测：透传优先级、自签 claim/exp、缺 secret 时只允许透传路径。

### T2.3 /meta → list_metrics / get_dimensions / 语义模型
- **文件**：新建 `datus_semantic_cube/adapter.py`
- **做**：实现 `list_metrics`（measures→`MetricDefinition`，path=Cube 名，分页走
  registry 的 `metric_catalog_page_size/max_pages`）、`get_dimensions`（按 measure
  反查 cube）、`get/list_semantic_models`（cubes）。错误映射：403/权限类 →
  `POLICY_REFUSED` 语义（对齐上游 read refusal 独立错误码），其余 →
  `SEMANTIC_ADAPTER_ERROR`。
- **验收**：mock httpx transport 单测（meta 样例 JSON 放
  `datus_semantic_cube/tests/fixtures/meta.json`）。

### T2.4 /load 与 /sql → query_metrics
- **做**：`query_metrics` 组装 Cube query（measures/dimensions/timeDimensions/
  filters/limit/order）→ `POST /cubejs-api/v1/load` → `QueryResult`；
  `dry_run=True` → `/sql` 返回编译 SQL；行数上限对齐 sql_guard 语义；时区用
  配置 `timezone`。
- **验收**：mock 单测覆盖：正常结果、空结果、limit 裁剪、dry_run、权限错误映射。

### T2.5 validate_semantic 与 sync_to_storage
- **做**：`validate_semantic` = `/meta` 可达性 200；`sync_to_storage` 委托
  `SemanticStorageManager.sync_from_adapter`（`datus/tools/semantic_tools/
  storage_sync.py`），记录同步统计。
- **验收**：mock 单测 + 与 storage_sync 的契约测试（同步计数正确）。

### T2.6 集成测试（真实 Cube）✅ 已实现（提交 1403a63e）
- 自包含 fixture：官方 cubejs/cube:latest + cubestore + postgres（orders 表）
  组网；live 测试 5/5 通过（meta/维度/分组计数/dry_run/validate），按
  CUBE_LIVE_URL/CUBE_LIVE_SECRET 门控，无环境自动跳过。
- live 发现并修复：新版 Cube /sql 响应外层多包一层（两种格式都兼容）。
- **T3.5 进度（精确记录）**：适配器侧端到端已通——bootstrap-kb
  --from_adapter cube 从 live Cube 取出全部指标并送达 storage_sync；
  卡点在本机 Lance 向量写入的内部错误（"Spill"，环境级、确定性复现、
  与分支代码无关）。恢复时第一步：对该数据源切 kb.search.mode=fts 绕过
  向量后端重试；多租户 cubeOrgId 路径仍需 GienBI bank 栈。
- **做**：`tests/integration/test_cube_adapter_live.py`，标记 `@pytest.mark.
  integration`；用 GienBI dev Cube（`cubejs-bank` 容器，需带测试 org 的 model
  目录）。跑 list/query/sql 三条路径。
- **验收**：live 用例通过（无环境时跳过并记录）。

---

## M3 engine 切换 + CLI

### T3.1 agent.yml cube 条目与解析验证
- **文件**：`conf/agent.yml.example`（semantic_layer 注释段补 cube 示例）
- **做**：示例含 `api_url/api_secret/timeout/timezone`；验证
  `resolve_semantic_adapter()` 对 `metricflow + cube` 双条目 + `default: true`
  的解析与无默认时的报错。
- **验收**：`pytest unit_tests/configuration/ -k semantic -q` 补用例。

### T3.2 `/services` TUI 验证
- **做**：手工走查 `datus/cli/service_commands.py` 的 semantic_layer 分组：
  cube 条目可选中、set global default、set project default（`set_active_semantic`
  落 `.datus/config.yml`）、probe（即 `/meta` 可达性）。
- **验收**：TUI 操作录屏/截图留档；probe 对错误 api_url 返回失败提示。

### T3.3 `/engine` 薄别名
- **文件**：`datus/cli/slash_registry.py`（新 `SlashSpec`）、新建
  `datus/cli/engine_commands.py`
- **做**：`/engine`（显示 resolved adapter + 可用条目）、`/engine cube`
  （项目级，委托 `set_active_semantic`）、`/engine --global cube`（委托
  global-default 动作）；目标不存在时按 `resolve_semantic_adapter()` 现有报错
  列出可用项。零新机制，全部转发。
- **验收**：单测（命令解析/转发）+ REPL 手工验证切换后
  `list_metrics` 走 cube（日志可见 /load 或 /meta 调用）。

### T3.4 bootstrap-kb --from_adapter cube
- **文件**：`datus/agent/agent.py`（bootstrap_kb 分支）、
  `datus/tools/semantic_tools/storage_sync.py`（如需 cube 专有字段映射）
- **做**：`datus-agent bootstrap-kb --datasource <ds> --components metrics,
  semantic_model --from_adapter cube --kb-update-strategy overwrite`；指标别名按
  chat2agent `ingest_with_aliases` 模式展开（主记录+别名共享 element_id）；同步
  记录打 tenant 维度（对齐 T1.5）。
- **验收**：真实 Cube 元数据进 LanceDB（`~/.datus/data/<project>/datus_db/` 出现
  metric 表数据）；`search_metrics` 中文别名能召回。

### T3.5 工作流冒烟
- **做**：engine=cube 下跑 `metric_to_sql` 与 `ask_metrics` 工作流各 3 问；
  记录降级面实际表现（OSI 建模工具不可用提示是否友好）。
- **验收**：冒烟记录进 `design/m3_smoke.md`。

---

## M4 gienbi-policy 权限插件

### T4.1 插件骨架与 manifest
- **文件**：新建 `plugins/gienbi_policy/{datus-plugin.yml, __init__.py,
  runtime.py, permissions.py, cache.py}`
- **做**：manifest 声明 policy runtime 工厂；工厂返回实现四钩子的对象
  （`validate_context / before_sql_read / before_metric_read / after_read_result`），
  遵循 `datus/tools/policy_runtime.py` 的接口契约。
- **验收**：`pytest unit_tests/plugins/ -q` + manifest 解析用例。

### T4.2 权限读取（直读 MySQL + TTL 缓存）
- **做**：移植 chat2agent `resource_permission.py` 的查询逻辑：
  `user_resource_permission_flat`（VIEW 位）、`rel_subject_columns`（禁列）、
  `semantic_model` 行权限脚本、`role.type='ORG_OWNER'` 旁路；进程内 60s TTL、
  按 `(org, user)` 键控；连接复用 datus 现有 datasource 机制新增 mysql 条目。
- **验收**：对 SQLite fixture 假表的单测（权限矩阵：有/无/Owner/禁列/行规则）。

### T4.3 validate_context + before_metric_read
- **做**：`validate_context` 多租户模式下要求 gienbi_org_id/gienbi_user_id；
  `before_metric_read` 按 VIEW 位过滤指标清单，denial 写入结果元数据
  （沿用 permission_filtered_metrics 语义）。
- **验收**：单测覆盖过滤与旁路。

### T4.4 `before_metric_read` 接线（上游小改）
- **文件**：`datus/tools/func_tool/semantic_tools.py`（list/search/query 路径）
- **做**：在 SemanticTools 的三个入口调 `policy_runtime.before_metric_read`，
  纯增量；同步给上游 datus 提 PR（分支内先垫）。
- **验收**：`pytest unit_tests/tools/func_tool/ -q`；带插件时无权限指标不可见。

### T4.5 行级权限双引擎分发
- **做**：移植 `get_row_scope()` 转换（`permission_operator` AND/OR、
  deny-by-default）；engine=cube → 过滤条件经 policy_context 传给适配器，
  组装进 query filters（`datus_semantic_cube/adapter.py` 增加 filters 注入点）；
  engine=metricflow → `before_sql_read` 用 sqlglot 改写 SQL，无法表达即拒绝。
- **验收**：单测：MQL filters 注入正确、SQL 改写正确、不可表达拒绝且原因可读。

### T4.6 列屏蔽与权限矩阵 E2E ✅ 单测面完成（提交 ecafc72c→a209c229→d768655c）
- **评审修复（d768655c）补齐了关键接线**：行权限现在跑在真实数据路径
  （SemanticTools.query_metrics 调 before_sql_read）；Cube 适配器
  inject_row_filters 消费 row_filters 并入查询载荷；list_metrics 同样过
  指标权限过滤。
- **评审遗留缺口——已全部修复（对照 chat2agent 参照实现）**：
  1. ✅ 主体模型：读法改为 USER/ROLE/DEPT 并集（`_subject_where_clause`
     移植：role 经 rel_role_user+role、dept 经 user.dept_id），且发现并
     修复了更严重的问题——真实表是 subject_type/subject_id 结构而非
     user_id 列，旧 SQL 在真实库上根本跑不通。测试夹具同步改为真实
     表结构（SqliteSubjectFixture），角色/部门规则生效有测试守护；
  2. ✅ 列屏蔽补 arrow 路径（pyarrow Table drop_columns）；
  3. ✅ cube 数值比较符改回 gt/gte/lt/lte（原误映射为日期操作符）。
- **仍待 live 环境**：权限矩阵 E2E（tests/e2e/test_permission_matrix.py）、
  query_metrics 结果形态的屏蔽接线（需确认生产调用点后接）。

---

## M5 评估与决策

### T5.1 semantic_layer benchmark 在 cube 引擎重跑
- **做**：`benchmark_semantic_layer` 配置指向 cube 引擎跑测试集，产出准确率
  对比（metricflow vs cube 同题）。
- **验收**：报告落 `design/m5_benchmark.md`。

### T5.2 权限矩阵回归 + 延迟对比
- **做**：T4.6 E2E 回归；`desc`/`ask_metrics`/`query_metrics` 三类操作在
  cube 引擎的 P50/P90 与 chat2agent 同题对比（含 GienAI/生产网关两档）。
- **验收**：延迟表进报告。

### T5.3 attribution 降级决策
- **做**：`attribution_analyze` 在 cube 引擎跑对比（SQL 归因 vs 禁用），按数据
  定案并回写设计文档 D-补充。
- **验收**：决策记录进 `design/datus-agent-cube.md`。

---

## M6（可选）拆包与增强

- `datus_semantic_cube` 平移至独立 `datus-semantic-adapter` 仓库；
- 指标定时增量同步（`updated_at` 或全量重刷 + 失败告警）；
- 术语层（`agent_terminology` 等价物）评估进 subject_tree/文档 KB。

## 执行中发现的问题（顺手记录）

- **上游 bug**：`datus/cli/main.py:316-320`（`_resolve_default_datasource`）把
  `load_agent_config` 的异常吞掉后打印裸 `--help` 并以 0 退出——配置错误被伪装成
  usage 输出，排障极具误导性（M0 期间实测踩坑：家目录项目 overlay 引用了已被
  改写掉的 `default_datasource: california_schools`，表现为"从 ~ 运行 datus -p
  只打印帮助"）。修法：异常时打印真实错误信息并以非 0 退出。候选上游 PR，
  排在 M4.4 的 PR 一起提。

---

## 提交与验证纪律

1. 每个任务 = 一次提交，信息格式 `[Mx.y] <摘要>`（对齐仓库现有
   `[BugFix]/[Enhancement]` 风格）。
2. 提交前必跑：该任务"验收"列出的命令 + `scripts/smoke_chat.sh`。
3. 涉及上游文件的改动（T1.5–T1.7、T4.4）保持加法式，每阶段结束跑
   `git merge main --no-commit --no-ff` 预检合并冲突面。
4. 凭据纪律：Cube secret / GienBI MySQL 凭据只进环境变量，禁止进
   agent.yml/文档/测试 fixture 明文。
