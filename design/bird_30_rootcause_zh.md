# BIRD 30 题逐题根因分析（Cube 直接映射路径，Round-3）

> 数据来源：analyze29.json（重放映射+执行+金标 diff）。Q20 已答对不列。

## 根因分布总览

| 代码 | 根因 | 题号 | 数量 |
|---|---|---|---|
| R1 | 适配器 where 操作符长尾（实际条件: Schools.Charter = 'Y' AN | 4,11,23,27 | 4 |
| R2b | 成员名错位（LLM 写了 Schools.MailStreet；生成模型实际名带 Total | 3,19,29 | 3 |
| R3 | 过滤/排序格式长尾（LLM 产出的值或组合超出解析器） | 5,7,9,12,13,17,24,26,28 | 9 |
| R4 | 查询语义错误（跨 cube join 下的成员/聚合语义） | 6,8,10,15,18,22,25 | 7 |
| R5 | 数据/SQL 执行错误 | 14 | 1 |
| W1 | 数值/行不匹配（含 LLM 附加展示列导致的比对误判可能，需人工看 diff） | 0,1,2,16,21 | 5 |

## 第 0 题 [simple] — W1

**中文**: Alameda County 的 K-12 学校中，符合条件的免费餐比例最高是多少？

**上轮阶段**: done｜**本轮执行**: 成功

**LLM 载荷**: metrics=['Frpm.percentEligibleFreeK12Total']｜dims=['Frpm.schoolName', 'Frpm.countyName']｜where=`Frpm.countyName = 'Alameda'`｜order=['-Frpm.percentEligibleFreeK12Total']｜limit=1

**根因**: 数值/行不匹配（含 LLM 附加展示列导致的比对误判可能，需人工看 diff）

**修复归属**: 逐例：见下方 diff

**金标行**: [["1.0"]]

**Cube 行**: [{"Frpm.schoolName": "Infant and Preschool Program", "Frpm.countyName": "Alameda", "Frpm.percentEligibleFreeK12Total": null}]

<details><summary>金标 SQL</summary>

```sql
SELECT `Free Meal Count (K-12)` / `Enrollment (K-12)` FROM frpm WHERE `County Name` = 'Alameda' ORDER BY (CAST(`Free Meal Count (K-12)` AS REAL) / `Enrollment (K-12)`) DESC LIMIT 1
```
</details>

## 第 1 题 [moderate] — W1

**中文**: 请列出续读学校中5-17岁学生符合条件的免费餐率最低的三个值。

**上轮阶段**: done｜**本轮执行**: 成功

**LLM 载荷**: metrics=['Frpm.percentEligibleFreeAges517Total']｜dims=['Frpm.schoolName', 'Frpm.educationalOptionType']｜where=`Frpm.educationalOptionType = 'Continuation'`｜order=['Frpm.percentEligibleFreeAges517Total']｜limit=3

**根因**: 数值/行不匹配（含 LLM 附加展示列导致的比对误判可能，需人工看 diff）

**修复归属**: 逐例：见下方 diff

**金标行**: [["0.043478260869565216"], ["0.07042253521126761"], ["0.11363636363636363"]]

<details><summary>金标 SQL</summary>

```sql
SELECT `Free Meal Count (Ages 5-17)` / `Enrollment (Ages 5-17)` FROM frpm WHERE `Educational Option Type` = 'Continuation School' AND `Free Meal Count (Ages 5-17)` / `Enrollment (Ages 5-17)` IS NOT NULL ORDER BY `Free Meal Count (Ages 5-17)` / `Enrollment (Ages 5-17)` ASC LIMIT 3
```
</details>

## 第 2 题 [simple] — W1

**中文**: 请列出弗雷斯诺县教育局所有特许学校的邮政编码。

**上轮阶段**: done｜**本轮执行**: 成功

**LLM 载荷**: metrics=['Schools.schoolsCount']｜dims=['Schools.Zip']｜where=`Schools.Charter = 'Y' AND Schools.SOC = 'Fresno County Office of Education'`｜order=[]｜limit=None

**根因**: 数值/行不匹配（含 LLM 附加展示列导致的比对误判可能，需人工看 diff）

**修复归属**: 逐例：见下方 diff

**金标行**: [["93726-5309"], ["93628-9602"], ["93706-2611"], ["93726-5208"], ["93706-2819"]]

<details><summary>金标 SQL</summary>

```sql
SELECT T2.Zip FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T1.`District Name` = 'Fresno County Office of Education' AND T1.`Charter School (Y/N)` = 1
```
</details>

## 第 3 题 [simple] — R2b

**中文**: K-12 学生中 FRPM 计数最高的学校的完整邮寄街道地址是什么？

**上轮阶段**: cube｜**本轮执行**: 失败

**LLM 载荷**: metrics=['Schools.MailStreet']｜dims=[]｜where=`None`｜order=['-Frpm.enrollmentK12Total']｜limit=1

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"type":"UserError","error":"'MailStreet' not found for path 'Schools.MailStreet'"}

**根因**: 成员名错位（LLM 写了 Schools.MailStreet；生成模型实际名带 Total 后缀或不同驼峰）

**修复归属**: E1 成员名对齐器（fuzzy→canonical）

**金标行**: [["14429 South Downey Avenue"]]

<details><summary>金标 SQL</summary>

```sql
SELECT T2.MailStreet FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode ORDER BY T1.`FRPM Count (K-12)` DESC LIMIT 1
```
</details>

## 第 4 题 [moderate] — R1

**中文**: 请列出2000年1月1日之后开设的直接由特许资金资助的学校电话号码。

**上轮阶段**: cube｜**本轮执行**: 失败

**LLM 载荷**: metrics=['Schools.schoolsCount']｜dims=['Schools.Phone']｜where=`Schools.Charter = 'Y' AND Schools.OpenDate > '2000-01-01'`｜order=[]｜limit=None

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube adapter supports equality, IN lists and simple comparisons in `where` (e.g. "Cube.dim = 'v'" / "Cube.dim IN ('a','b')" / "Cube.

**根因**: 适配器 where 操作符长尾（实际条件: Schools.Charter = 'Y' AND Schools.OpenDate > '2000-01-01'）

**修复归属**: E-R1 操作符扩展(BETWEEN/LIKE/IS NOT NULL)

**金标行**: [["None"], ["(510) 596-8901"], ["None"], ["(510) 686-4131"], ["(510) 452-2063"]]

<details><summary>金标 SQL</summary>

```sql
SELECT T2.Phone FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T1.`Charter Funding Type` = 'Directly funded' AND T1.`Charter School (Y/N)` = 1 AND T2.OpenDate > '2000-01-01'
```
</details>

## 第 5 题 [simple] — R3

**中文**: 在SAT考试中数学平均分大于400的学校中，有多少所是纯虚拟学校？

**上轮阶段**: cube｜**本轮执行**: 失败

**LLM 载荷**: metrics=['Satscores.satscoresCount']｜dims=[]｜where=`Satscores.AvgScrMathTotal > 400 AND Schools.Virtual = 'F'`｜order=[]｜limit=None

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"error":"Invalid query format: \"havingFilters\" is not allowed"}

**根因**: 过滤/排序格式长尾（LLM 产出的值或组合超出解析器）

**修复归属**: E-R3 格式容错 + 报告具体字段

**金标行**: [["4"]]

<details><summary>金标 SQL</summary>

```sql
SELECT COUNT(DISTINCT T2.School) FROM satscores AS T1 INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode WHERE T2.Virtual = 'F' AND T1.AvgScrMath > 400
```
</details>

## 第 6 题 [simple] — R4

**中文**: 在SAT考生超过500人的学校中，请列出磁校或提供磁项目的学校。

**上轮阶段**: cube｜**本轮执行**: 失败

**LLM 载荷**: metrics=['Satscores.NumTstTakrTotal']｜dims=['Schools.School', 'Schools.Magnet']｜where=`Satscores.NumTstTakr > 500 AND Schools.Magnet = '1'`｜order=[]｜limit=None

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"type":"UserError","error":"Can't find join path to join 'Schools', 'Satscores'"}

**根因**: 查询语义错误（跨 cube join 下的成员/聚合语义）

**修复归属**: E-R4 生成模型 join/成员审查

**金标行**: [["Millikan High"], ["Polytechnic High"], ["Troy High"]]

<details><summary>金标 SQL</summary>

```sql
SELECT T2.School FROM satscores AS T1 INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode WHERE T2.Magnet = 1 AND T1.NumTstTakr > 500
```
</details>

## 第 7 题 [simple] — R3

**中文**: SAT 成绩超过 1500 分的考生人数最多的学校的电话号码是多少？

**上轮阶段**: cube｜**本轮执行**: 失败

**LLM 载荷**: metrics=['Satscores.NumGE1500Total']｜dims=['Schools.Phone']｜where=`Satscores.NumGE1500Total > 0`｜order=['-Satscores.NumGE1500Total']｜limit=1

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"error":"Invalid query format: \"havingFilters\" is not allowed"}

**根因**: 过滤/排序格式长尾（LLM 产出的值或组合超出解析器）

**修复归属**: E-R3 格式容错 + 报告具体字段

**金标行**: [["(213) 241-1000"]]

<details><summary>金标 SQL</summary>

```sql
SELECT T2.Phone FROM satscores AS T1 INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode ORDER BY T1.NumGE1500 DESC LIMIT 1
```
</details>

## 第 8 题 [simple] — R4

**中文**: K-12 学生 FRPM 人数最多的学校中，SAT 考生人数是多少？

**上轮阶段**: cube｜**本轮执行**: 失败

**LLM 载荷**: metrics=['Satscores.NumTstTakrTotal']｜dims=['Frpm.schoolName']｜where=`Frpm.fRPMCountK12Total > 0`｜order=['-Frpm.fRPMCountK12Total']｜limit=1

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"type":"UserError","error":"Can't find join path to join 'Frpm', 'Satscores'"}

**根因**: 查询语义错误（跨 cube join 下的成员/聚合语义）

**修复归属**: E-R4 生成模型 join/成员审查

**金标行**: [["459"]]

<details><summary>金标 SQL</summary>

```sql
SELECT NumTstTakr FROM satscores WHERE cds = ( SELECT CDSCode FROM frpm ORDER BY `FRPM Count (K-12)` DESC LIMIT 1 )
```
</details>

## 第 9 题 [simple] — R3

**中文**: 在SAT数学平均分超过560的学校中，有多少所是直拨特许资金支持的特许学校？

**上轮阶段**: cube｜**本轮执行**: 失败

**LLM 载荷**: metrics=['Satscores.satscoresCount']｜dims=[]｜where=`Satscores.AvgScrMathTotal > 560`｜order=[]｜limit=None

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"error":"Invalid query format: \"havingFilters\" is not allowed"}

**根因**: 过滤/排序格式长尾（LLM 产出的值或组合超出解析器）

**修复归属**: E-R3 格式容错 + 报告具体字段

**金标行**: [["2"]]

<details><summary>金标 SQL</summary>

```sql
SELECT COUNT(T2.`School Code`) FROM satscores AS T1 INNER JOIN frpm AS T2 ON T1.cds = T2.CDSCode WHERE T1.AvgScrMath > 560 AND T2.`Charter Funding Type` = 'Directly funded'
```
</details>

## 第 10 题 [simple] — R4

**中文**: 在SAT考试中阅读平均分最高的学校，其5-17岁学生的FRPM人数是多少？

**上轮阶段**: cube｜**本轮执行**: 失败

**LLM 载荷**: metrics=['Satscores.AvgScrReadTotal', 'Frpm.fRPMCountAges517Total']｜dims=['Satscores.sname']｜where=`None`｜order=['-Satscores.AvgScrReadTotal']｜limit=1

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"type":"UserError","error":"Can't find join path to join 'Satscores', 'Frpm'"}

**根因**: 查询语义错误（跨 cube join 下的成员/聚合语义）

**修复归属**: E-R4 生成模型 join/成员审查

**金标行**: [["136.0"]]

<details><summary>金标 SQL</summary>

```sql
SELECT T2.`FRPM Count (Ages 5-17)` FROM satscores AS T1 INNER JOIN frpm AS T2 ON T1.cds = T2.CDSCode ORDER BY T1.AvgScrRead DESC LIMIT 1
```
</details>

## 第 11 题 [simple] — R1

**中文**: 请列出总入学人数超过500的学校代码。

**上轮阶段**: cube｜**本轮执行**: 失败

**LLM 载荷**: metrics=['Frpm.enrollmentK12Total', 'Frpm.enrollmentAges517Total']｜dims=['Frpm.schoolCode']｜where=`Frpm.enrollmentK12Total + Frpm.enrollmentAges517Total > 500`｜order=[]｜limit=None

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube adapter supports equality, IN lists and simple comparisons in `where` (e.g. "Cube.dim = 'v'" / "Cube.dim IN ('a','b')" / "Cube.

**根因**: 适配器 where 操作符长尾（实际条件: Frpm.enrollmentK12Total + Frpm.enrollmentAges517Total > 500）

**修复归属**: E-R1 操作符扩展(BETWEEN/LIKE/IS NOT NULL)

**金标行**: [["01100170109835"], ["01100170112607"], ["01100170124172"], ["01100170125567"], ["01100176001788"]]

<details><summary>金标 SQL</summary>

```sql
SELECT T2.CDSCode FROM schools AS T1 INNER JOIN frpm AS T2 ON T1.CDSCode = T2.CDSCode WHERE T2.`Enrollment (K-12)` + T2.`Enrollment (Ages 5-17)` > 500
```
</details>

## 第 12 题 [moderate] — R3

**中文**: 在SAT优秀率超过0.3的学校中，5-17岁学生符合条件的免费餐率最高是多少？

**上轮阶段**: cube｜**本轮执行**: 失败

**LLM 载荷**: metrics=['Satscores.NumGE1500Total', 'Satscores.NumTstTakrTotal', 'Frpm.freeMealCountAges517Total', 'Frpm.enrollmentAges517Total']｜dims=[]｜where=`Satscores.NumTstTakrTotal > 0`｜order=['-Frpm.freeMealCountAges517Total']｜limit=1

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"error":"Invalid query format: \"havingFilters\" is not allowed"}

**根因**: 过滤/排序格式长尾（LLM 产出的值或组合超出解析器）

**修复归属**: E-R3 格式容错 + 报告具体字段

**金标行**: [["0.9049079754601227"]]

<details><summary>金标 SQL</summary>

```sql
SELECT MAX(CAST(T1.`Free Meal Count (Ages 5-17)` AS REAL) / T1.`Enrollment (Ages 5-17)`) FROM frpm AS T1 INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds WHERE CAST(T2.NumGE1500 AS REAL) / T2.NumTstTakr > 0.3
```
</details>

## 第 13 题 [simple] — R3

**中文**: 请列出SAT优秀率前三的学校的电话号码。

**上轮阶段**: cube｜**本轮执行**: 失败

**LLM 载荷**: metrics=['Satscores.NumGE1500Total', 'Satscores.NumTstTakrTotal', 'Schools.Phone']｜dims=['Schools.Phone']｜where=`Satscores.NumTstTakrTotal > 0`｜order=['-Satscores.NumGE1500Total / Satscores.NumTstTakrTotal']｜limit=3

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"error":"Invalid query format: \"order.Satscores.NumGE1500Total / Satscores.NumTstTakrTotal\" is not allow

**根因**: 过滤/排序格式长尾（LLM 产出的值或组合超出解析器）

**修复归属**: E-R3 格式容错 + 报告具体字段

**金标行**: [["(714) 220-3055"], ["(562) 229-7745"], ["(408) 366-7700"]]

<details><summary>金标 SQL</summary>

```sql
SELECT T1.Phone FROM schools AS T1 INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds ORDER BY CAST(T2.NumGE1500 AS REAL) / T2.NumTstTakr DESC LIMIT 3
```
</details>

## 第 14 题 [simple] — R5

**中文**: 按入学人数（5-17岁）从高到低排序，列出前五所学校，并提供它们的NCES学校识别码。

**上轮阶段**: cube｜**本轮执行**: 失败

**LLM 载荷**: metrics=['Frpm.enrollmentAges517Total']｜dims=['Schools.NCESSchool']｜where=`None`｜order=['-Frpm.enrollmentAges517Total']｜limit=5

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"error":"Error: column reference \"CDSCode\" is ambiguous"}

**根因**: 数据/SQL 执行错误

**修复归属**: 逐例分析

**金标行**: [["11707"], ["04653"], ["08283"], ["02751"], ["03050"]]

<details><summary>金标 SQL</summary>

```sql
SELECT T1.NCESSchool FROM schools AS T1 INNER JOIN frpm AS T2 ON T1.CDSCode = T2.CDSCode ORDER BY T2.`Enrollment (Ages 5-17)` DESC LIMIT 5
```
</details>

## 第 15 题 [simple] — R4

**中文**: 哪个活跃学区在阅读方面的平均分最高？

**上轮阶段**: cube｜**本轮执行**: 失败

**LLM 载荷**: metrics=['Satscores.AvgScrReadTotal']｜dims=['Satscores.dname']｜where=`Schools.StatusType = 'Active'`｜order=['-Satscores.AvgScrReadTotal']｜limit=1

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"type":"UserError","error":"Can't find join path to join 'Satscores', 'Schools'"}

**根因**: 查询语义错误（跨 cube join 下的成员/聚合语义）

**修复归属**: E-R4 生成模型 join/成员审查

**金标行**: [["Palo Alto Unified"]]

<details><summary>金标 SQL</summary>

```sql
SELECT T1.District FROM schools AS T1 INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds WHERE T1.StatusType = 'Active' ORDER BY T2.AvgScrRead DESC LIMIT 1
```
</details>

## 第 16 题 [simple] — W1

**中文**: 合并后的阿拉米达县中，考生人数少于100的学校有多少所？

**上轮阶段**: done｜**本轮执行**: 成功

**LLM 载荷**: metrics=['Satscores.satscoresCount']｜dims=[]｜where=`Satscores.NumTstTakr < 100`｜order=[]｜limit=None

**根因**: 数值/行不匹配（含 LLM 附加展示列导致的比对误判可能，需人工看 diff）

**修复归属**: 逐例：见下方 diff

**金标行**: [["1"]]

**Cube 行**: [{"Satscores.satscoresCount": "357"}]

<details><summary>金标 SQL</summary>

```sql
SELECT COUNT(T1.CDSCode) FROM schools AS T1 INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds WHERE T1.StatusType = 'Merged' AND T2.NumTstTakr < 100 AND T1.County = 'Lake'
```
</details>

## 第 17 题 [simple] — R3

**中文**: 按写作平均分对学校进行排名，其中分数大于499，并显示其特许学校编号。

**上轮阶段**: cube｜**本轮执行**: 失败

**LLM 载荷**: metrics=['Satscores.AvgScrWriteTotal']｜dims=['Schools.CharterNum', 'Satscores.sname']｜where=`Satscores.AvgScrWriteTotal > 499`｜order=['-Satscores.AvgScrWriteTotal']｜limit=10

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"error":"Invalid query format: \"havingFilters\" is not allowed"}

**根因**: 过滤/排序格式长尾（LLM 产出的值或组合超出解析器）

**修复归属**: E-R3 格式容错 + 报告具体字段

**金标行**: [["0210", "630", "1"], ["0890", "593", "2"], ["0290", "582", "3"], ["0930", "579", "4"], ["1169", "576", "5"]]

<details><summary>金标 SQL</summary>

```sql
SELECT CharterNum, AvgScrWrite, RANK() OVER (ORDER BY AvgScrWrite DESC) AS WritingScoreRank FROM schools AS T1  INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds WHERE T2.AvgScrWrite > 499 AND CharterNum is not null
```
</details>

## 第 18 题 [simple] — R4

**中文**: 弗雷斯诺（直接资助）有多少学校的考生人数不超过250人？

**上轮阶段**: cube｜**本轮执行**: 失败

**LLM 载荷**: metrics=['Satscores.satscoresCount']｜dims=[]｜where=`Satscores.NumTstTakr <= 250 AND Schools.DOC = 'Directly Funded' AND Schools.County = 'Fresno'`｜order=[]｜limit=None

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"type":"UserError","error":"Can't find join path to join 'Satscores', 'Schools'"}

**根因**: 查询语义错误（跨 cube join 下的成员/聚合语义）

**修复归属**: E-R4 生成模型 join/成员审查

**金标行**: [["14"]]

<details><summary>金标 SQL</summary>

```sql
SELECT COUNT(T1.CDSCode) FROM frpm AS T1 INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds WHERE T1.`Charter Funding Type` = 'Directly funded' AND T1.`County Name` = 'Fresno' AND T2.NumTstTakr <= 250
```
</details>

## 第 19 题 [simple] — R2b

**中文**: 数学平均分最高的学校的电话号码是多少？

**上轮阶段**: cube｜**本轮执行**: 失败

**LLM 载荷**: metrics=['Satscores.AvgScrMathTotal', 'Schools.Phone']｜dims=['Schools.School']｜where=`None`｜order=['-Satscores.AvgScrMathTotal']｜limit=1

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"type":"UserError","error":"'Phone' not found for path 'Schools.Phone'"}

**根因**: 成员名错位（LLM 写了 Schools.Phone；生成模型实际名带 Total 后缀或不同驼峰）

**修复归属**: E1 成员名对齐器（fuzzy→canonical）

**金标行**: [["(408) 366-7700"]]

<details><summary>金标 SQL</summary>

```sql
SELECT T1.Phone FROM schools AS T1 INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds ORDER BY T2.AvgScrMath DESC LIMIT 1
```
</details>

## 第 21 题 [simple] — W1

**中文**: 在洛杉矶，有多少所学校的 K-12 阶段免费餐人数超过 500 人，但免费或减价餐人数少于 700 人？

**上轮阶段**: done｜**本轮执行**: 成功

**LLM 载荷**: metrics=['Schools.schoolsCount']｜dims=[]｜where=`Schools.City = 'Los Angeles' AND Frpm.freeMealCountK12 > 500 AND Frpm.fRPMCountK12 < 700`｜order=[]｜limit=None

**根因**: 数值/行不匹配（含 LLM 附加展示列导致的比对误判可能，需人工看 diff）

**修复归属**: 逐例：见下方 diff

**金标行**: [["249"]]

**Cube 行**: [{"Schools.schoolsCount": "89"}]

<details><summary>金标 SQL</summary>

```sql
SELECT COUNT(CDSCode) FROM frpm WHERE `County Name` = 'Los Angeles' AND `Free Meal Count (K-12)` > 500 AND `FRPM Count (K-12)`< 700
```
</details>

## 第 22 题 [simple] — R4

**中文**: 康特拉科斯塔县中考生人数最多的学校是哪所？

**上轮阶段**: cube｜**本轮执行**: 失败

**LLM 载荷**: metrics=['Satscores.NumTstTakrTotal']｜dims=['Schools.School']｜where=`Schools.County = 'Contra Costa'`｜order=['-Satscores.NumTstTakrTotal']｜limit=1

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"type":"UserError","error":"Can't find join path to join 'Schools', 'Satscores'"}

**根因**: 查询语义错误（跨 cube join 下的成员/聚合语义）

**修复归属**: E-R4 生成模型 join/成员审查

**金标行**: [["Dougherty Valley High"]]

<details><summary>金标 SQL</summary>

```sql
SELECT sname FROM satscores WHERE cname = 'Contra Costa' AND sname IS NOT NULL ORDER BY NumTstTakr DESC LIMIT 1
```
</details>

## 第 23 题 [moderate] — R1

**中文**: 列出 K-12 和 5-17 岁之间入学人数差异超过 30 的学校名称，并提供这些学校的完整街道地址。

**上轮阶段**: cube｜**本轮执行**: 失败

**LLM 载荷**: metrics=['Frpm.enrollmentK12Total', 'Frpm.enrollmentAges517Total', 'Schools.schoolsCount']｜dims=['Frpm.schoolName', 'Schools.Street']｜where=`Frpm.enrollmentK12Total - Frpm.enrollmentAges517Total > 30`｜order=[]｜limit=None

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube adapter supports equality, IN lists and simple comparisons in `where` (e.g. "Cube.dim = 'v'" / "Cube.dim IN ('a','b')" / "Cube.

**根因**: 适配器 where 操作符长尾（实际条件: Frpm.enrollmentK12Total - Frpm.enrollmentAges517Total > 30）

**修复归属**: E-R1 操作符扩展(BETWEEN/LIKE/IS NOT NULL)

**金标行**: [["Alameda County Community", "313 West Winton Avenue"], ["California School for the Deaf-Fremont", "39350 Gallaudet Drive"], ["Alameda High", "2201 Encinal Avenue"], ["Encinal High", "210 Central Avenue"], ["Island High

<details><summary>金标 SQL</summary>

```sql
SELECT T1.School, T1.Street FROM schools AS T1 INNER JOIN frpm AS T2 ON T1.CDSCode = T2.CDSCode WHERE T2.`Enrollment (K-12)` - T2.`Enrollment (Ages 5-17)` > 30
```
</details>

## 第 24 题 [moderate] — R3

**中文**: 请列出 K-12 阶段符合免费餐食资格比例超过 0.1 且考生成绩大于或等于 1500 的学校名称？

**上轮阶段**: cube｜**本轮执行**: 失败

**LLM 载荷**: metrics=['Frpm.schoolName', 'Frpm.percentEligibleFreeK12Total', 'Satscores.NumGE1500Total']｜dims=['Frpm.schoolName']｜where=`Frpm.percentEligibleFreeK12Total > 0.1 AND Satscores.NumGE1500Total > 0`｜order=[]｜limit=None

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"error":"Invalid query format: \"havingFilters\" is not allowed"}

**根因**: 过滤/排序格式长尾（LLM 产出的值或组合超出解析器）

**修复归属**: E-R3 格式容错 + 报告具体字段

**金标行**: [["Clovis North High"], ["Clovis West High"], ["Buchanan High"], ["Clovis East High"], ["Clovis High"]]

<details><summary>金标 SQL</summary>

```sql
SELECT T2.`School Name` FROM satscores AS T1 INNER JOIN frpm AS T2 ON T1.cds = T2.CDSCode WHERE CAST(T2.`Free Meal Count (K-12)` AS REAL) / T2.`Enrollment (K-12)` > 0.1 AND T1.NumGE1500 > 0
```
</details>

## 第 25 题 [moderate] — R4

**中文**: 列出 Riverside 中 SAT 平均数学分数的平均值大于 400 的学校，这些学校的资助类型是什么？

**上轮阶段**: cube｜**本轮执行**: 失败

**LLM 载荷**: metrics=['Satscores.AvgScrMathTotal', 'Satscores.satscoresCount']｜dims=['Schools.School', 'Schools.FundingType']｜where=`Schools.County = 'Riverside'`｜order=[]｜limit=None

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"type":"UserError","error":"Can't find join path to join 'Schools', 'Satscores'"}

**根因**: 查询语义错误（跨 cube join 下的成员/聚合语义）

**修复归属**: E-R4 生成模型 join/成员审查

**金标行**: [["Arlington High", "None"], ["John W. North High", "None"], ["Martin Luther King Jr. High", "None"], ["Polytechnic High", "None"], ["Ramona High", "None"]]

<details><summary>金标 SQL</summary>

```sql
SELECT T1.sname, T2.`Charter Funding Type` FROM satscores AS T1 INNER JOIN frpm AS T2 ON T1.cds = T2.CDSCode WHERE T2.`District Name` LIKE 'Riverside%' GROUP BY T1.sname, T2.`Charter Funding Type` HAVING CAST(SUM(T1.AvgScrMath) AS REAL) / COUNT(T1.cds) > 400
```
</details>

## 第 26 题 [moderate] — R3

**中文**: 列出蒙特雷高中名称及其完整通信地址，这些高中15-17岁年龄段享受免费或减价餐的人数超过800人？

**上轮阶段**: cube｜**本轮执行**: 失败

**LLM 载荷**: metrics=['Schools.schoolsCount', 'Frpm.freeMealCountAges517Total']｜dims=['Frpm.schoolName', 'Schools.Street', 'Schools.City', 'Schools.State', 'Schools.Zip']｜where=`Frpm.freeMealCountAges517Total > 800 AND Schools.City = 'Monterey' AND Frpm.highGrade >= 12`｜order=[]｜limit=None

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"error":"Invalid query format: \"havingFilters\" is not allowed"}

**根因**: 过滤/排序格式长尾（LLM 产出的值或组合超出解析器）

**修复归属**: E-R3 格式容错 + 报告具体字段

**金标行**: [["Alisal High", "777 Williams Road", "Salinas", "CA", "93905-1907"], ["Everett Alvarez High", "1900 Independence Boulevard", "Salinas", "CA", "93906-5300"], ["North Salinas High", "55 Kip Drive", "Salinas", "CA", "93906

<details><summary>金标 SQL</summary>

```sql
SELECT T1.`School Name`, T2.Street, T2.City, T2.State, T2.Zip FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T2.County = 'Monterey' AND T1.`Free Meal Count (Ages 5-17)` > 800 AND T1.`School Type` = 'High Schools (Public)'
```
</details>

## 第 27 题 [moderate] — R1

**中文**: 1991年之后开设或2000年之前关闭的学校，其写作平均分是多少？请列出学校名称及对应的分数。如果有的话，请同时列出这些学校的通信编号。

**上轮阶段**: cube｜**本轮执行**: 失败

**LLM 载荷**: metrics=['Satscores.AvgScrWriteTotal', 'Schools.Phone']｜dims=['Schools.School', 'Schools.Phone']｜where=`(Schools.OpenDate > '1991-12-31' OR Schools.ClosedDate < '2000-01-01')`｜order=[]｜limit=None

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube adapter supports equality, IN lists and simple comparisons in `where` (e.g. "Cube.dim = 'v'" / "Cube.dim IN ('a','b')" / "Cube.

**根因**: 适配器 where 操作符长尾（实际条件: (Schools.OpenDate > '1991-12-31' OR Schools.ClosedDate < '2000-01-01')）

**修复归属**: E-R1 操作符扩展(BETWEEN/LIKE/IS NOT NULL)

**金标行**: [["FAME Public Charter", "None", "None"], ["Envision Academy for Arts & Technology", "None", "(510) 596-8901"], ["Aspire California College Preparatory Academy", "None", "None"], ["Community School for Creative Education

<details><summary>金标 SQL</summary>

```sql
SELECT T2.School, T1.AvgScrWrite, T2.Phone FROM schools AS T2 LEFT JOIN satscores AS T1 ON T2.CDSCode = T1.cds WHERE strftime('%Y', T2.OpenDate) > '1991' OR strftime('%Y', T2.ClosedDate) < '2000'
```
</details>

## 第 28 题 [challenging] — R3

**中文**: 考虑由地方资助的学校的 K-12 入学人数与 15-17 岁入学人数之间的平均差异，列出差异高于此平均值的学校名称和 DOC 类型。

**上轮阶段**: cube｜**本轮执行**: 失败

**LLM 载荷**: metrics=['Frpm.enrollmentK12Total', 'Frpm.enrollmentAges517Total', 'Frpm.enrollmentK12Total - Frpm.enrollmentAges517Total']｜dims=['Frpm.schoolName', 'Frpm.dOC']｜where=`Frpm.dOC = 'Locally Funded'`｜order=[]｜limit=None

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"error":"Invalid query format: \"measures[2]\" with value \"Frpm.enrollmentK12Total - Frpm.enrollmentAges5

**根因**: 过滤/排序格式长尾（LLM 产出的值或组合超出解析器）

**修复归属**: E-R3 格式容错 + 报告具体字段

**金标行**: [["Mountain Oaks", "00"], ["Castle Rock", "00"], ["Charter Community School Home Study Academy", "00"], ["Clovis Online Charter", "54"], ["Washington Elementary", "52"]]

<details><summary>金标 SQL</summary>

```sql
SELECT T2.School, T2.DOC FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T2.FundingType = 'Locally funded' AND (T1.`Enrollment (K-12)` - T1.`Enrollment (Ages 5-17)`) > (SELECT AVG(T3.`Enrollment (K-12)` - T3.`Enrollment (Ages 5-17)`) FROM frpm AS T3 INNER JOIN schools AS T4 ON T3.CDSCode = T4.CDSCode WHERE T4.FundingType = 'Locally funded')
```
</details>

## 第 29 题 [simple] — R2b

**中文**: 招生人数最多的K-12学校是什么时候开学的？

**上轮阶段**: cube｜**本轮执行**: 失败

**LLM 载荷**: metrics=['Frpm.enrollmentK12Total']｜dims=['Frpm.schoolName', 'Frpm.OpenDate']｜where=`Frpm.highGrade = '12'`｜order=['-Frpm.enrollmentK12Total']｜limit=1

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"type":"UserError","error":"'OpenDate' not found for path 'Frpm.OpenDate'"}

**根因**: 成员名错位（LLM 写了 Frpm.OpenDate；生成模型实际名带 Total 后缀或不同驼峰）

**修复归属**: E1 成员名对齐器（fuzzy→canonical）

**金标行**: [["2006-08-29"]]

<details><summary>金标 SQL</summary>

```sql
SELECT T2.OpenDate FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode ORDER BY T1.`Enrollment (K-12)` DESC LIMIT 1
```
</details>
