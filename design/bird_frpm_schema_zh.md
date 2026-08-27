# frpm 表字段中文对照（BIRD california_schools）

> FRPM（Free or Reduced Price Meals，免费/减价餐）资格统计表，9,986 行，
> 是 BIRD california_schools **题目密度最高的表**（前 30 题里约三分之二涉
> 及它）。主键/关联键 `CDSCode`，与 `schools` 表关联。
>
> ⚠️ 列名**带空格和括号**（如 `Enrollment (K-12)`）——SQL 里必须加引号；
> 这也是查询失败的高发点。MetricFlow 需要在 `sql_query` 里先别名成
> snake_case（见 tests/data/semantic_models/bird_school/frpm.yml）。

## 主键

| 字段 | 类型 | 中文含义 |
|---|---|---|
| CDSCode | TEXT | 加州教育署学校唯一编码，关联 schools.CDSCode |

## 学年

| 字段 | 类型 | 中文含义 |
|---|---|---|
| Academic Year | TEXT | 学年（如 2014-2015；BIRD 第 72 题考 `BETWEEN 2014 AND 2015` 的边界写法） |

## 行政归属（与 schools 冗余，方便单表查）

| 字段 | 类型 | 中文含义 |
|---|---|---|
| County Code | TEXT | 县代码 |
| County Name | TEXT | 县名（第 16/18/21 题：'Los Angeles'/'Fresno' 等） |
| District Code | INTEGER | 学区代码 |
| District Name | TEXT | 学区名（第 2 题：'Fresno County Office of Education'；第 25 题 LIKE 'Riverside%'） |
| School Code | INTEGER | 学校代码 |
| School Name | TEXT | 学校名 |

## 学校属性（与 schools 冗余，但口径更细）

| 字段 | 类型 | 中文含义 |
|---|---|---|
| District Type | TEXT | 学区类型 |
| School Type | TEXT | 学校类型（第 26 题：'High Schools (Public)'=公立高中） |
| Educational Option Type | TEXT | 教育选项类型（第 1 题：'Continuation School'=续读学校；SPECON 等特教类型见 schools.EdOpsCode） |
| NSLP Provision Status | TEXT | 全国学校午餐计划供餐状态（第 75/76/83 题：'Breakfast Provision 2' / 'Lunch Provision 2' / 'Multiple Provision Types'） |
| Charter School (Y/N) | INTEGER | 是否特许学校（1/0；⚠️ evidence 全用此列判断"特许"，别用 schools.Charter——第 2/4/35 题） |
| Charter School Number | TEXT | 特许编号 |
| Charter Funding Type | TEXT | 特许资金类型（第 4/9/18/25/66 题：'Directly funded'=直接拨款） |
| IRC | INTEGER | IRC 标志（Immigrant Refugee Program 移民难民计划） |
| Low Grade / High Grade | TEXT | 最低/最高年级（第 20/76 题：Low=9 且 High=12 即高中段；数值型内容存 TEXT） |

## 核心：K-12 系列指标（4 个数一组 × 2 个人群 × 比率）

| 字段 | 类型 | 中文含义 |
|---|---|---|
| Enrollment (K-12) | REAL | K-12 入学人数（分母） |
| Free Meal Count (K-12) | REAL | K-12 免费餐人数（分子；第 0/21 题考点） |
| Percent (%) Eligible Free (K-12) | REAL | 免费餐资格比例（**实测本表存 0-1 小数**，虽列名带 % 号；已逐行核对 379 行与 Count÷Enrollment 完全等价——直接用此列安全） |
| FRPM Count (K-12) | REAL | 免费+减价餐总人数（第 3/8/10 题的 "FRPM count"） |
| Percent (%) Eligible FRPM (K-12) | REAL | FRPM 资格比例（同为 0-1 小数） |
| *(第三行同构)* | — | （每组计数列紧跟一列现成比率列） |

## 核心：Ages 5-17 系列指标（与上组完全对称）

| 字段 | 类型 | 中文含义 |
|---|---|---|
| Enrollment (Ages 5-17) | REAL | 5-17 岁入学人数（第 23 题"两人群差值 >30"、第 28 题"差值高于平均"的第二个操作数） |
| Free Meal Count (Ages 5-17) | REAL | 5-17 岁免费餐人数（第 1/26/33 题分子） |
| Percent (%) Eligible Free (Ages 5-17) | REAL | 该人群免费餐资格比例% |
| FRPM Count (Ages 5-17) | REAL | 5-17 岁免费+减价餐总人数（第 10/26/73 题考点） |
| Percent (%) Eligible FRPM (Ages 5-17) | REAL | 该人群 FRPM 资格比例% |

## 其他

| 字段 | 类型 | 中文含义 |
|---|---|---|
| 2013-14 CALPADS Fall 1 Certification Status | INTEGER | CALPADS 数据认证状态标志（无题涉及） |

## BIRD 高频考点对照（从题目反查）

| 题目词汇（英文原文 → 中文理解） | 对应字段 | 备注 |
|---|---|---|
| eligible free rate（符合条件的免费餐率） | Free Meal Count ÷ Enrollment（同人群配对） | **必自己除**，注意 K-12 与 Ages 5-17 别配错人群（第 1 题陷阱）；比率是 0-1 小数 |
| free meals vs free or reduced price meals | Free Meal Count vs FRPM Count | "免费餐"≠"免费+减价餐"，第 21 题两个条件分别取不同列 |
| continuation school（续读学校） | Educational Option Type = 'Continuation School' | 不是 School Type |
| direct charter-funded（直接拨款特许校） | Charter Funding Type = 'Directly funded' + Charter School (Y/N)=1 | 常组合出现（第 4 题） |
| percent eligible ... more than 0.1 | Percent(%) 列即 0-1 小数，可直接比较 | 第 24 题阈值 0.1 直接用（实测修正：此表无百分/小数单位陷阱） |
| enrollment difference K-12 与 Ages 5-17 | 两列相减（第 11/23/28 题） | 跨"两组指标"比较题 |
| High Schools (Public)（公立高中） | School Type 完整值匹配 | 模糊说"high school"时要精确到全串（第 26 题） |

## 与 Cube 模型（M5 实验）的对应

`/tmp/cube-live/model/Frpm.js` 已建模：enrollmentK12 / freeMealK12 /
frpmEligibleK12（SUM）、freeMealRateK12（SUM/SUM COALESCE 比率）、
Ages 5-17 三兄弟 + 两个比率、schoolType/districtType/eduOptionType 维度。
带空格原始列经 sql 模板直接引用（Cube 自动加引号），无需别名。
