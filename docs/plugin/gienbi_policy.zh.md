# GienBI 权限插件

`gienbi_policy` 插件把 Datus 接入 GienBI 平台的权限模型与多租户身份。它包含两个协作部分：

| 组成 | 作用 |
|---|---|
| `GienBIAuthProvider`（认证） | 把网关注入的可信请求头映射到请求上下文：租户、用户、agent 作用域，以及可选的 Cube JWT 透传。 |
| `GienbiPolicyRuntime`（策略） | 在 agent 的每次读取上执行 GienBI 权限模型：指标级 VIEW 门禁、行级过滤、列屏蔽。 |

## 身份请求头

`GienBIAuthProvider` 从网关注入的请求头读取身份，绝不盲信客户端自报的租户：

| 请求头 | 映射到 | 用途 |
|---|---|---|
| `X-GienBI-OrgId` | `tenant_id` | 租户边界（KB 存储、会话目录、Cube `cubeOrgId`） |
| `X-GienBI-UserId` | `user_id` | 会话作用域与权限主体 |
| `X-GienBI-AgentId` | `sub_agent_name` | KB 读取边界（可选） |
| `X-GienBI-CubeToken` | Cube JWT | Cube 引擎的透传令牌（可选） |

字面 org id `default` 会被拒收——它保留给单租户回退路径，放行会模糊租户边界。

## 启用多租户

```yaml
api:
  auth_provider:
    class: datus.api.auth.gienbi_provider:GienBIAuthProvider
    kwargs:
      multi_tenant: true
  multi_tenant: true          # 部署级开关
```

任一层级的 `multi_tenant: true` 生效时：缺少 org/user 身份的请求会被
fail-closed 拒绝（而不是降级为匿名），无法承载租户身份的 provider 在加载期
即被拒收。

多租户会贯穿到请求之下的每一层：

- 知识库存储行携带 `tenant_id` 列，storage key 以
  `{tenant}:{datasource}:{row}` 为前缀；
- 会话目录分层为 `{session_dir}/{tenant}/{scope}/`；
- Cube 引擎按租户签发 JWT（`cubeOrgId = {tenant}A`），除非请求带
  `X-GienBI-CubeToken` 透传。

## 策略执行

策略运行时在 agent 读取路径的四个点生效：

| 钩子 | 执行内容 |
|---|---|
| `validate_context` | 多租户模式下，拒绝没有可用 GienBI org/user 身份的请求。 |
| `before_metric_read` | 对调用方无 VIEW 权限的指标——列表与查询都不可见。 |
| `before_sql_read` | 把行级过滤注入 SQL WHERE；cube 引擎下同样的规则编译为 Cube `filters`（维度）与 `havingFilters`（度量）。 |
| `after_read_result` | 对返回行中的受限列做屏蔽。 |

权限主体是 GienBI 权限表中该用户的 USER、ROLE、DEPT 三类条目的并集。
运行时通过 MySQL 读取这些表，并按用户缓存 `permission_cache_ttl_seconds`
秒（默认 60s）。

## 配置

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

凭据一律用环境变量引用，不要写进文件。项目级用 `./.datus/config.yml` 的
`plugins: {gienbi_policy: {enabled: true}}` 激活（见
[插件](introduction.zh.md)）。

## 当前限制

- 行策略语法覆盖 GienBI 规则树的子集（维度值条件）；维度侧行级作用域
  （限制维度值本身的存在性）是后续工作（Cube 计划 B10）。
- 多租户 Cube JWT 路径（`cubeOrgId`）与权限矩阵已有单测覆盖；端到端验证
  需要真实 GienBI 环境（Cube 计划 B6/B7）。
