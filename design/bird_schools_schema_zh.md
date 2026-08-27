# schools 表字段中文对照（BIRD california_schools）

> 学校主表，17,686 行。主键 `CDSCode`（加州教育署 CDS 编码），与
> `frpm`、`satscores` 两表经 `CDSCode` 关联。

## 标识

| 字段 | 类型 | 中文含义 |
|---|---|---|
| CDSCode | TEXT | 加州教育署（CDE）学校唯一编码：县码-区码-校码 组合 |
| NCESDist | TEXT | 美国国家教育统计中心（NCES）学区编号 |
| NCESSchool | TEXT | NCES 学校编号 |

## 名称与状态

| 字段 | 类型 | 中文含义 |
|---|---|---|
| StatusType | TEXT | 学校状态（Active=运营中 / Closed=已关闭 / Merged=已合并） |
| County | TEXT | 县名 |
| District | TEXT | 学区名 |
| School | TEXT | 学校名 |

## 实体地址

| 字段 | 类型 | 中文含义 |
|---|---|---|
| Street | TEXT | 街道地址（完整非缩写） |
| StreetAbr | TEXT | 街道地址（缩写） |
| City | TEXT | 所在城市 |
| Zip | TEXT | 邮编 |
| State | TEXT | 州（CA=加利福尼亚） |

## 邮寄地址（可以和实体地址不同）

| 字段 | 类型 | 中文含义 |
|---|---|---|
| MailStreet | TEXT | 邮寄街道地址（完整） |
| MailStrAbr | TEXT | 邮寄街道地址（缩写） |
| MailCity | TEXT | 邮寄城市 |
| MailZip | TEXT | 邮寄邮编 |
| MailState | TEXT | 邮寄州 |

## 联系方式

| 字段 | 类型 | 中文含义 |
|---|---|---|
| Phone | TEXT | 电话号码 |
| Ext | TEXT | 分机号 |
| Website | TEXT | 网站 |

## 时间

| 字段 | 类型 | 中文含义 |
|---|---|---|
| OpenDate | DATE | 开办日期 |
| ClosedDate | DATE | 关闭日期（未关闭为空） |
| LastUpdate | DATE | 记录最后更新日期 |

## 特性与类型编码

| 字段 | 类型 | 中文含义 |
|---|---|---|
| Charter | INTEGER | 是否特许学校（1=是 / 0=否） |
| CharterNum | TEXT | 特许编号（如 '00D2'、'0040'） |
| FundingType | TEXT | 资金类型（Directly funded=直接拨款 / Locally funded=本地拨款） |
| DOC | TEXT | 管理机构代码（52=小学区 / 54=联合学区 / 31=州立特校 / 62=初中等 …） |
| DOCType | TEXT | 管理机构类型名称 |
| SOC | TEXT | 办学主体代码（11=青少年管教设施 / 62=初级中学 / 69=县级社区日校 …） |
| SOCType | TEXT | 办学主体类型名称（Youth Authority Facilities 等） |
| EdOpsCode | TEXT | 教育运营方式代码（SSS=州立特校 / SPECON=特教联合体 …） |
| EdOpsName | TEXT | 教育运营方式名称 |
| EILCode | TEXT | 教育层次代码（HS=高中 / K-9 跨度等 …） |
| EILName | TEXT | 教育层次名称 |
| GSoffered | TEXT | 提供的年级跨度（K-8、K-12 …） |
| GSserved | TEXT | 实际服务的年级跨度 |
| Virtual | TEXT | 虚拟办学形式（F=完全线下 / P=部分线上） |
| Magnet | INTEGER | 是否磁校或提供磁石项目（1=是 / 0=否） |
| Latitude | REAL | 纬度 |
| Longitude | REAL | 经度 |

## 管理员 1/2/3（每校最多三位）

| 字段 | 中文含义 |
|---|---|
| AdmFName1 / AdmLName1 / AdmEmail1 | 第一管理员：名 / 姓 / 邮箱 |
| AdmFName2 / AdmLName2 / AdmEmail2 | 第二管理员：同上 |
| AdmFName3 / AdmLName3 / AdmEmail3 | 第三管理员：同上 |

## BIRD 高频考点对照（从题目反查）

| 题目词汇 | 对应字段 | 备注 |
|---|---|---|
| charter school（特许学校） | Charter = 1 | frpm 表也有同义列；第 60/61 题指的是 schools.Charter |
| directly funded / locally funded | FundingType | 两种取值见上 |
| merged / active / closed | StatusType | 第 16/49/55-56 题考点 |
| virtual = 'F' | "纯线下/实体学校"——注意 F 是 false 的缩写但语义是"非虚拟" | BIRD 陷阱之一（第 5/41/79 题） |
| Elementary School District / Unified School District / State Special Schools | DOC = 52 / 54 / 31 | 只给代码不给名（evidence 补） |
| Youth Authority Facilities (CEA) | SOC = 11 | |
| administrators' first/last name | AdmFName*/AdmLName* | 无独立管理员表，三组列平铺 |
