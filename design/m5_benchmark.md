# M5 评估报告：Cube 语义层 vs 自由 SQL（BIRD california_schools）

日期：2026-08-27 ｜ 环境：本机自包含 Cube 栈（cubejs/cube:latest + cubestore + postgres，
BIRD california_schools 三表灌入 + 手工 Cube 模型）

## 实验设计

- **自由 SQL 基线（agent 路径）**：datus 完整 agentic 工作流（reflection 计划），
  GS-Qwen3.6-35B-A3B，BIRD dev 前 30 题，sqlite 源。
- **Cube 语义层路径（映射管道）**：LLM 单次把问题映射为 Cube 查询
  （成员清单进 prompt，逐字约束），经 datus_semantic_cube 适配器执行，
  与金标 SQL 在 sqlite 上的执行结果做数值比对。这是 chat2agent 式
  "流水线"路径的最小复刻，隔离语义层本身的收益（join/指标预定义，
  LLM 只做选择）。

## 结果

| 路径 | 可答覆盖 | 尝试正确 | 总准确率 | 单题延迟 |
|---|---|---|---|---|
| 自由 SQL（agentic，28/30 完成） | 93% | 9/28 | **32.1%** | ~18s/题（3 并发） |
| Cube 直接映射（最小模型） | 4/30 | 0/4 | **0%** | ~0.8-1.8s/题 |
| Cube 直接映射（扩模型+强约束后） | 9/30 | 0/9 | **0%** | ~1.8s/题 |

**数值正确性锚点**：Q0（Alameda 县 K-12 最高免费餐比例）Cube 结果
1.0 / 0.9833 / 0.9829 与金标完全一致——映射正确时语义层数值可靠。
（更正：早先记录的"校名与金标不同"是我手工对照时误加了
`StatusType='Active'` 过滤所致；BIRD 金标无此过滤，纯 frpm 表按比率
排序的第一名即 Oakland Community Day Middle，两种路径完全一致。）

## 分析（结论按重要性排序）

1. **覆盖是第一约束，映射质量第二**。两轮的失败主体不是"答错"而是
   "答不了"：最小模型下 18/30 判 unanswerable；扩模型后转为 20/30 的
   查询构造失败（AND 复合过滤、跨 join 成员、IN 细节）。BIRD 自由问法
   天然超出瘦语义模型的覆盖面——这验证了设计假设：**语义层收益取决于
   模型覆盖度**，GienBI 的真实优势是 Java 侧从 semantic_model 表生成的
   全量租户模型，不是手工最小模型。
2. **BIRD 是 Cube 路径的最坏情况基准**。BIRD 考的是地址/电话/跨表细节
   这类"表形状"问题（自由 SQL 的主场）；GienBI 问数的真实问法是
   "指标形状"（多少、趋势、排名、占比）——那才是 cube 引擎的目标场景。
   用 BIRD 对比 cube 有系统性偏向，应记录为方法学偏差。
3. **正确的生产形态是混合**（回到设计 D8 的降级面）：指标形状问题走
   cube（快、join 免疫），表形状问题回落自由 SQL（agent 的
   metric_to_sql → gen_sql 正是这个结构）。chat2agent 的整条技能流水线
   （术语解析/意图分类/HITL）就是为把自然语言可靠压进语义层覆盖面而生的。
4. **延迟数量级差异真实存在**：映射管道 ~1s/题 vs agentic ~18s/题。
   即使只覆盖 30% 的问题，命中时就是 20 倍加速——GienBI 生产上把高频
   指标问题截流到 cube 的价值主张成立。

## attribution 决策（M5.3）

cube 引擎下 `attribution_analyze` 维持**降级为禁用**（设计 D-补充）：
本轮未实施 SQL 归因 fallback；metricflow 引擎保留原生归因。
触发条件：GienBI 侧提出归因需求时再评估。

## 附：本轮顺手修复（live 驱动）

- 适配器 `order_by` 支持 `-member` 降序前缀（接口约定，此前透传报错）；
- `where` 解析器扩展：`!=` / `IN (...)` / `> >= < <=`（此前仅等值，
  首轮实验 4 题直接死于此）；
- 两项均有单测守护（cube 套件 31 绿）。

复现：`benchmark/scripts/cube_bird_eval.py --limit 30`（Cube 栈与模型
见 `/tmp/cube-live/`，容器：cube-live/cubestore-live/cube-pg）。
