# BIRD 29 题三方完整对照：Cube 查询载荷 → 编译 SQL → 金标 SQL

> Q20 已答对不列。『未发送』= 载荷在适配器 where 解析阶段被拒，未到达 Cube。

## 第 0 题 [simple]（上轮结果: done）

**中文**: Alameda County 的 K-12 学校中，符合条件的免费餐比例最高是多少？

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Frpm.percentEligibleFreeK12Total"
 ],
 "dimensions": [
  "Frpm.schoolName",
  "Frpm.countyName"
 ],
 "where(适配器解析前)": "Frpm.countyName = 'Alameda'",
 "order_by": [
  "-Frpm.percentEligibleFreeK12Total"
 ],
 "limit": 1
}
```

**② Cube 编译出的 SQL**

```sql
SELECT "School Name" "frpm__school_name", "County Name" "frpm__county_name", sum(CAST("Percent (%) Eligible Free (K-12)" AS DOUBLE PRECISION)) "frpm__percent_eligible_free_k12_total" 
FROM  frpm  AS "frpm"
WHERE ("County Name" = $1)
GROUP BY 1, 2
ORDER BY  3  DESC
LIMIT 1
```

**③ 金标 SQL**

```sql
SELECT `Free Meal Count (K-12)` / `Enrollment (K-12)` FROM frpm WHERE `County Name` = 'Alameda' ORDER BY (CAST(`Free Meal Count (K-12)` AS REAL) / `Enrollment (K-12)`) DESC LIMIT 1
```

**Cube 执行行(前5)**: [{"Frpm.schoolName": "Infant and Preschool Program", "Frpm.countyName": "Alameda", "Frpm.percentEligibleFreeK12Total": null}]

**金标行(前5)**: [["1.0"]]

---

## 第 1 题 [moderate]（上轮结果: done）

**中文**: 请列出续读学校中5-17岁学生符合条件的免费餐率最低的三个值。

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Frpm.percentEligibleFreeAges517Total"
 ],
 "dimensions": [
  "Frpm.schoolName",
  "Frpm.educationalOptionType"
 ],
 "where(适配器解析前)": "Frpm.educationalOptionType = 'Continuation'",
 "order_by": [
  "Frpm.percentEligibleFreeAges517Total"
 ],
 "limit": 3
}
```

**② Cube 编译出的 SQL**

```sql
SELECT "School Name" "frpm__school_name", "Educational Option Type" "frpm__educational_option_type", sum(CAST("Percent (%) Eligible Free (Ages 5-17)" AS DOUBLE PRECISION)) "frpm__percent_eligible_free_ages517_total" 
FROM  frpm  AS "frpm"
WHERE ("Educational Option Type" = $1)
GROUP BY 1, 2
ORDER BY  3  ASC
LIMIT 3
```

**③ 金标 SQL**

```sql
SELECT `Free Meal Count (Ages 5-17)` / `Enrollment (Ages 5-17)` FROM frpm WHERE `Educational Option Type` = 'Continuation School' AND `Free Meal Count (Ages 5-17)` / `Enrollment (Ages 5-17)` IS NOT NULL ORDER BY `Free Meal Count (Ages 5-17)` / `Enrollment (Ages 5-17)` ASC LIMIT 3
```

**Cube 执行行(前5)**: []

**金标行(前5)**: [["0.043478260869565216"], ["0.07042253521126761"], ["0.11363636363636363"]]

---

## 第 2 题 [simple]（上轮结果: done）

**中文**: 请列出弗雷斯诺县教育局所有特许学校的邮政编码。

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Schools.schoolsCount"
 ],
 "dimensions": [
  "Schools.Zip"
 ],
 "where(适配器解析前)": "Schools.Charter = 'Y' AND Schools.SOC = 'Fresno County Office of Education'"
}
```

**② Cube 编译出的 SQL**

```sql
SELECT "Zip" "schools___zip", count(1) "schools__schools_count" 
FROM  schools  AS "schools"
WHERE ("Charter" = $1) AND ("SOC" = $2)
GROUP BY 1
ORDER BY  2  DESC
LIMIT 10000
```

**③ 金标 SQL**

```sql
SELECT T2.Zip FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T1.`District Name` = 'Fresno County Office of Education' AND T1.`Charter School (Y/N)` = 1
```

**Cube 执行行(前5)**: []

**金标行(前5)**: [["93726-5309"], ["93628-9602"], ["93706-2611"], ["93726-5208"], ["93706-2819"]]

---

## 第 3 题 [simple]（上轮结果: cube）

**中文**: K-12 学生中 FRPM 计数最高的学校的完整邮寄街道地址是什么？

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Schools.MailStreet"
 ],
 "dimensions": [],
 "order_by": [
  "-Frpm.enrollmentK12Total"
 ],
 "limit": 1
}
```

**② Cube 编译出的 SQL**

```（未编译：error_code=600002, error_message=Semantic adapter operation failed: Cube /sql returned 400: {"type":"UserError","error":"'MailStreet' not found for pa）```

**③ 金标 SQL**

```sql
SELECT T2.MailStreet FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode ORDER BY T1.`FRPM Count (K-12)` DESC LIMIT 1
```

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"type":"UserError","error":"'MailStreet' not found for path 'Schools.MailStreet'"}

**金标行(前5)**: [["14429 South Downey Avenue"]]

---

## 第 4 题 [moderate]（上轮结果: cube）

**中文**: 请列出2000年1月1日之后开设的直接由特许资金资助的学校电话号码。

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Schools.schoolsCount"
 ],
 "dimensions": [
  "Schools.Phone"
 ],
 "where(适配器解析前)": "Schools.Charter = 'Y' AND Schools.OpenDate > '2000-01-01'"
}
```

**② Cube 编译出的 SQL**

```（未编译：error_code=600002, error_message=Semantic adapter operation failed: Cube adapter supports equality, IN lists and simple comparisons in `where` (e.g. "）```

**③ 金标 SQL**

```sql
SELECT T2.Phone FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T1.`Charter Funding Type` = 'Directly funded' AND T1.`Charter School (Y/N)` = 1 AND T2.OpenDate > '2000-01-01'
```

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube adapter supports equality, IN lists and simple comparisons in `where` (e.g. "Cube.dim = 'v'" / "Cube.dim IN

**金标行(前5)**: [["None"], ["(510) 596-8901"], ["None"], ["(510) 686-4131"], ["(510) 452-2063"]]

---

## 第 5 题 [simple]（上轮结果: cube）

**中文**: 在SAT考试中数学平均分大于400的学校中，有多少所是纯虚拟学校？

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Satscores.satscoresCount"
 ],
 "dimensions": [],
 "where(适配器解析前)": "Satscores.AvgScrMathTotal > 400 AND Schools.Virtual = 'F'"
}
```

**② Cube 编译出的 SQL**

```（未编译：error_code=600002, error_message=Semantic adapter operation failed: Cube /sql returned 400: {"error":"Invalid query format: \"havingFilters\" is not a）```

**③ 金标 SQL**

```sql
SELECT COUNT(DISTINCT T2.School) FROM satscores AS T1 INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode WHERE T2.Virtual = 'F' AND T1.AvgScrMath > 400
```

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"error":"Invalid query format: \"havingFilters\" is not allowed"}

**金标行(前5)**: [["4"]]

---

## 第 6 题 [simple]（上轮结果: cube）

**中文**: 在SAT考生超过500人的学校中，请列出磁校或提供磁项目的学校。

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Satscores.NumTstTakrTotal"
 ],
 "dimensions": [
  "Schools.School",
  "Schools.Magnet"
 ],
 "where(适配器解析前)": "Satscores.NumTstTakr > 500 AND Schools.Magnet = '1'"
}
```

**② Cube 编译出的 SQL**

```（未编译：error_code=600002, error_message=Semantic adapter operation failed: Cube /sql returned 400: {"type":"UserError","error":"Can't find join path to join ）```

**③ 金标 SQL**

```sql
SELECT T2.School FROM satscores AS T1 INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode WHERE T2.Magnet = 1 AND T1.NumTstTakr > 500
```

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"type":"UserError","error":"Can't find join path to join 'Schools', 'Satscores'"}

**金标行(前5)**: [["Millikan High"], ["Polytechnic High"], ["Troy High"]]

---

## 第 7 题 [simple]（上轮结果: cube）

**中文**: SAT 成绩超过 1500 分的考生人数最多的学校的电话号码是多少？

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Satscores.NumGE1500Total"
 ],
 "dimensions": [
  "Schools.Phone"
 ],
 "where(适配器解析前)": "Satscores.NumGE1500Total > 0",
 "order_by": [
  "-Satscores.NumGE1500Total"
 ],
 "limit": 1
}
```

**② Cube 编译出的 SQL**

```（未编译：error_code=600002, error_message=Semantic adapter operation failed: Cube /sql returned 400: {"error":"Invalid query format: \"havingFilters\" is not a）```

**③ 金标 SQL**

```sql
SELECT T2.Phone FROM satscores AS T1 INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode ORDER BY T1.NumGE1500 DESC LIMIT 1
```

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"error":"Invalid query format: \"havingFilters\" is not allowed"}

**金标行(前5)**: [["(213) 241-1000"]]

---

## 第 8 题 [simple]（上轮结果: cube）

**中文**: K-12 学生 FRPM 人数最多的学校中，SAT 考生人数是多少？

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Satscores.NumTstTakrTotal"
 ],
 "dimensions": [
  "Frpm.schoolName"
 ],
 "where(适配器解析前)": "Frpm.fRPMCountK12Total > 0",
 "order_by": [
  "-Frpm.fRPMCountK12Total"
 ],
 "limit": 1
}
```

**② Cube 编译出的 SQL**

```（未编译：error_code=600002, error_message=Semantic adapter operation failed: Cube /sql returned 400: {"type":"UserError","error":"Can't find join path to join ）```

**③ 金标 SQL**

```sql
SELECT NumTstTakr FROM satscores WHERE cds = ( SELECT CDSCode FROM frpm ORDER BY `FRPM Count (K-12)` DESC LIMIT 1 )
```

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"type":"UserError","error":"Can't find join path to join 'Frpm', 'Satscores'"}

**金标行(前5)**: [["459"]]

---

## 第 9 题 [simple]（上轮结果: cube）

**中文**: 在SAT数学平均分超过560的学校中，有多少所是直拨特许资金支持的特许学校？

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Satscores.satscoresCount"
 ],
 "dimensions": [],
 "where(适配器解析前)": "Satscores.AvgScrMathTotal > 560"
}
```

**② Cube 编译出的 SQL**

```（未编译：error_code=600002, error_message=Semantic adapter operation failed: Cube /sql returned 400: {"error":"Invalid query format: \"havingFilters\" is not a）```

**③ 金标 SQL**

```sql
SELECT COUNT(T2.`School Code`) FROM satscores AS T1 INNER JOIN frpm AS T2 ON T1.cds = T2.CDSCode WHERE T1.AvgScrMath > 560 AND T2.`Charter Funding Type` = 'Directly funded'
```

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"error":"Invalid query format: \"havingFilters\" is not allowed"}

**金标行(前5)**: [["2"]]

---

## 第 10 题 [simple]（上轮结果: cube）

**中文**: 在SAT考试中阅读平均分最高的学校，其5-17岁学生的FRPM人数是多少？

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Satscores.AvgScrReadTotal",
  "Frpm.fRPMCountAges517Total"
 ],
 "dimensions": [
  "Satscores.sname"
 ],
 "order_by": [
  "-Satscores.AvgScrReadTotal"
 ],
 "limit": 1
}
```

**② Cube 编译出的 SQL**

```（未编译：error_code=600002, error_message=Semantic adapter operation failed: Cube /sql returned 400: {"type":"UserError","error":"Can't find join path to join ）```

**③ 金标 SQL**

```sql
SELECT T2.`FRPM Count (Ages 5-17)` FROM satscores AS T1 INNER JOIN frpm AS T2 ON T1.cds = T2.CDSCode ORDER BY T1.AvgScrRead DESC LIMIT 1
```

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"type":"UserError","error":"Can't find join path to join 'Satscores', 'Frpm'"}

**金标行(前5)**: [["136.0"]]

---

## 第 11 题 [simple]（上轮结果: cube）

**中文**: 请列出总入学人数超过500的学校代码。

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Frpm.enrollmentK12Total",
  "Frpm.enrollmentAges517Total"
 ],
 "dimensions": [
  "Frpm.schoolCode"
 ],
 "where(适配器解析前)": "Frpm.enrollmentK12Total + Frpm.enrollmentAges517Total > 500"
}
```

**② Cube 编译出的 SQL**

```（未编译：error_code=600002, error_message=Semantic adapter operation failed: Cube adapter supports equality, IN lists and simple comparisons in `where` (e.g. "）```

**③ 金标 SQL**

```sql
SELECT T2.CDSCode FROM schools AS T1 INNER JOIN frpm AS T2 ON T1.CDSCode = T2.CDSCode WHERE T2.`Enrollment (K-12)` + T2.`Enrollment (Ages 5-17)` > 500
```

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube adapter supports equality, IN lists and simple comparisons in `where` (e.g. "Cube.dim = 'v'" / "Cube.dim IN

**金标行(前5)**: [["01100170109835"], ["01100170112607"], ["01100170124172"], ["01100170125567"], ["01100176001788"]]

---

## 第 12 题 [moderate]（上轮结果: cube）

**中文**: 在SAT优秀率超过0.3的学校中，5-17岁学生符合条件的免费餐率最高是多少？

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Satscores.NumGE1500Total",
  "Satscores.NumTstTakrTotal",
  "Frpm.freeMealCountAges517Total",
  "Frpm.enrollmentAges517Total"
 ],
 "dimensions": [],
 "where(适配器解析前)": "Satscores.NumTstTakrTotal > 0",
 "order_by": [
  "-Frpm.freeMealCountAges517Total"
 ],
 "limit": 1
}
```

**② Cube 编译出的 SQL**

```（未编译：error_code=600002, error_message=Semantic adapter operation failed: Cube /sql returned 400: {"error":"Invalid query format: \"havingFilters\" is not a）```

**③ 金标 SQL**

```sql
SELECT MAX(CAST(T1.`Free Meal Count (Ages 5-17)` AS REAL) / T1.`Enrollment (Ages 5-17)`) FROM frpm AS T1 INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds WHERE CAST(T2.NumGE1500 AS REAL) / T2.NumTstTakr > 0.3
```

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"error":"Invalid query format: \"havingFilters\" is not allowed"}

**金标行(前5)**: [["0.9049079754601227"]]

---

## 第 13 题 [simple]（上轮结果: cube）

**中文**: 请列出SAT优秀率前三的学校的电话号码。

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Satscores.NumGE1500Total",
  "Satscores.NumTstTakrTotal",
  "Schools.Phone"
 ],
 "dimensions": [
  "Schools.Phone"
 ],
 "where(适配器解析前)": "Satscores.NumTstTakrTotal > 0",
 "order_by": [
  "-Satscores.NumGE1500Total / Satscores.NumTstTakrTotal"
 ],
 "limit": 3
}
```

**② Cube 编译出的 SQL**

```（未编译：error_code=600002, error_message=Semantic adapter operation failed: Cube /sql returned 400: {"error":"Invalid query format: \"order.Satscores.NumGE150）```

**③ 金标 SQL**

```sql
SELECT T1.Phone FROM schools AS T1 INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds ORDER BY CAST(T2.NumGE1500 AS REAL) / T2.NumTstTakr DESC LIMIT 3
```

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"error":"Invalid query format: \"order.Satscores.NumGE1500Total / Satscores.NumTstTakr

**金标行(前5)**: [["(714) 220-3055"], ["(562) 229-7745"], ["(408) 366-7700"]]

---

## 第 14 题 [simple]（上轮结果: cube）

**中文**: 按入学人数（5-17岁）从高到低排序，列出前五所学校，并提供它们的NCES学校识别码。

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Frpm.enrollmentAges517Total"
 ],
 "dimensions": [
  "Schools.NCESSchool"
 ],
 "order_by": [
  "-Frpm.enrollmentAges517Total"
 ],
 "limit": 5
}
```

**② Cube 编译出的 SQL**

```sql
 WITH 
cte_0 AS (  SELECT "keys"."schools___n_c_e_s_school" "schools___n_c_e_s_school", sum(CAST("Enrollment (Ages 5-17)" AS DOUBLE PRECISION)) "frpm__enrollment_ages517_total" 
  FROM (SELECT DISTINCT "NCESSchool" "schools___n_c_e_s_school", "CDSCode" "frpm___c_d_s_code" 
  FROM  schools  AS "frpm_key_schools"
  LEFT JOIN  frpm  AS "frpm_key_frpm" ON "frpm_key_schools"."CDSCode" = "frpm_key_frpm"."CDSCode") AS "keys"
  LEFT JOIN  frpm  AS "frpm_key_frpm" ON (("keys"."frpm___c_d_s_code" = "CDSCode"))
  GROUP BY 1)
SELECT "fk_aggregate"."schools___n_c_e_s_school" "schools___n_c_e_s_school", "fk_aggregate"."frpm__enrollment_ages517_total" "frpm__enrollment_ages517_total" 
FROM  cte_0  AS "fk_aggregate"
ORDER BY  2  DESC
LIMIT 5
```

**③ 金标 SQL**

```sql
SELECT T1.NCESSchool FROM schools AS T1 INNER JOIN frpm AS T2 ON T1.CDSCode = T2.CDSCode ORDER BY T2.`Enrollment (Ages 5-17)` DESC LIMIT 5
```

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"error":"Error: column reference \"CDSCode\" is ambiguous"}

**金标行(前5)**: [["11707"], ["04653"], ["08283"], ["02751"], ["03050"]]

---

## 第 15 题 [simple]（上轮结果: cube）

**中文**: 哪个活跃学区在阅读方面的平均分最高？

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Satscores.AvgScrReadTotal"
 ],
 "dimensions": [
  "Satscores.dname"
 ],
 "where(适配器解析前)": "Schools.StatusType = 'Active'",
 "order_by": [
  "-Satscores.AvgScrReadTotal"
 ],
 "limit": 1
}
```

**② Cube 编译出的 SQL**

```（未编译：error_code=600002, error_message=Semantic adapter operation failed: Cube /sql returned 400: {"type":"UserError","error":"Can't find join path to join ）```

**③ 金标 SQL**

```sql
SELECT T1.District FROM schools AS T1 INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds WHERE T1.StatusType = 'Active' ORDER BY T2.AvgScrRead DESC LIMIT 1
```

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"type":"UserError","error":"Can't find join path to join 'Satscores', 'Schools'"}

**金标行(前5)**: [["Palo Alto Unified"]]

---

## 第 16 题 [simple]（上轮结果: done）

**中文**: 合并后的阿拉米达县中，考生人数少于100的学校有多少所？

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Satscores.satscoresCount"
 ],
 "dimensions": [],
 "where(适配器解析前)": "Satscores.NumTstTakr < 100"
}
```

**② Cube 编译出的 SQL**

```sql
SELECT count(1) "satscores__satscores_count" 
FROM  satscores  AS "satscores"
WHERE ("NumTstTakr" < $1)
LIMIT 10000
```

**③ 金标 SQL**

```sql
SELECT COUNT(T1.CDSCode) FROM schools AS T1 INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds WHERE T1.StatusType = 'Merged' AND T2.NumTstTakr < 100 AND T1.County = 'Lake'
```

**Cube 执行行(前5)**: [{"Satscores.satscoresCount": "357"}]

**金标行(前5)**: [["1"]]

---

## 第 17 题 [simple]（上轮结果: cube）

**中文**: 按写作平均分对学校进行排名，其中分数大于499，并显示其特许学校编号。

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Satscores.AvgScrWriteTotal"
 ],
 "dimensions": [
  "Schools.CharterNum",
  "Satscores.sname"
 ],
 "where(适配器解析前)": "Satscores.AvgScrWriteTotal > 499",
 "order_by": [
  "-Satscores.AvgScrWriteTotal"
 ],
 "limit": 10
}
```

**② Cube 编译出的 SQL**

```（未编译：error_code=600002, error_message=Semantic adapter operation failed: Cube /sql returned 400: {"error":"Invalid query format: \"havingFilters\" is not a）```

**③ 金标 SQL**

```sql
SELECT CharterNum, AvgScrWrite, RANK() OVER (ORDER BY AvgScrWrite DESC) AS WritingScoreRank FROM schools AS T1  INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds WHERE T2.AvgScrWrite > 499 AND CharterNum is not null
```

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"error":"Invalid query format: \"havingFilters\" is not allowed"}

**金标行(前5)**: [["0210", "630", "1"], ["0890", "593", "2"], ["0290", "582", "3"], ["0930", "579", "4"], ["1169", "576", "5"]]

---

## 第 18 题 [simple]（上轮结果: cube）

**中文**: 弗雷斯诺（直接资助）有多少学校的考生人数不超过250人？

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Satscores.satscoresCount"
 ],
 "dimensions": [],
 "where(适配器解析前)": "Satscores.NumTstTakr <= 250 AND Schools.DOC = 'Directly Funded' AND Schools.County = 'Fresno'"
}
```

**② Cube 编译出的 SQL**

```（未编译：error_code=600002, error_message=Semantic adapter operation failed: Cube /sql returned 400: {"type":"UserError","error":"Can't find join path to join ）```

**③ 金标 SQL**

```sql
SELECT COUNT(T1.CDSCode) FROM frpm AS T1 INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds WHERE T1.`Charter Funding Type` = 'Directly funded' AND T1.`County Name` = 'Fresno' AND T2.NumTstTakr <= 250
```

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"type":"UserError","error":"Can't find join path to join 'Satscores', 'Schools'"}

**金标行(前5)**: [["14"]]

---

## 第 19 题 [simple]（上轮结果: cube）

**中文**: 数学平均分最高的学校的电话号码是多少？

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Satscores.AvgScrMathTotal",
  "Schools.Phone"
 ],
 "dimensions": [
  "Schools.School"
 ],
 "order_by": [
  "-Satscores.AvgScrMathTotal"
 ],
 "limit": 1
}
```

**② Cube 编译出的 SQL**

```（未编译：error_code=600002, error_message=Semantic adapter operation failed: Cube /sql returned 400: {"type":"UserError","error":"'Phone' not found for path 'S）```

**③ 金标 SQL**

```sql
SELECT T1.Phone FROM schools AS T1 INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds ORDER BY T2.AvgScrMath DESC LIMIT 1
```

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"type":"UserError","error":"'Phone' not found for path 'Schools.Phone'"}

**金标行(前5)**: [["(408) 366-7700"]]

---

## 第 21 题 [simple]（上轮结果: done）

**中文**: 在洛杉矶，有多少所学校的 K-12 阶段免费餐人数超过 500 人，但免费或减价餐人数少于 700 人？

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Schools.schoolsCount"
 ],
 "dimensions": [],
 "where(适配器解析前)": "Schools.City = 'Los Angeles' AND Frpm.freeMealCountK12 > 500 AND Frpm.fRPMCountK12 < 700"
}
```

**② Cube 编译出的 SQL**

```sql
SELECT count(1) "schools__schools_count" 
FROM  schools  AS "schools"
LEFT JOIN  frpm  AS "frpm" ON "schools"."CDSCode" = "frpm"."CDSCode"
WHERE ("City" = $1) AND ("Free Meal Count (K-12)" > $2) AND ("FRPM Count (K-12)" < $3)
LIMIT 10000
```

**③ 金标 SQL**

```sql
SELECT COUNT(CDSCode) FROM frpm WHERE `County Name` = 'Los Angeles' AND `Free Meal Count (K-12)` > 500 AND `FRPM Count (K-12)`< 700
```

**Cube 执行行(前5)**: [{"Schools.schoolsCount": "89"}]

**金标行(前5)**: [["249"]]

---

## 第 22 题 [simple]（上轮结果: cube）

**中文**: 康特拉科斯塔县中考生人数最多的学校是哪所？

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Satscores.NumTstTakrTotal"
 ],
 "dimensions": [
  "Schools.School"
 ],
 "where(适配器解析前)": "Schools.County = 'Contra Costa'",
 "order_by": [
  "-Satscores.NumTstTakrTotal"
 ],
 "limit": 1
}
```

**② Cube 编译出的 SQL**

```（未编译：error_code=600002, error_message=Semantic adapter operation failed: Cube /sql returned 400: {"type":"UserError","error":"Can't find join path to join ）```

**③ 金标 SQL**

```sql
SELECT sname FROM satscores WHERE cname = 'Contra Costa' AND sname IS NOT NULL ORDER BY NumTstTakr DESC LIMIT 1
```

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"type":"UserError","error":"Can't find join path to join 'Schools', 'Satscores'"}

**金标行(前5)**: [["Dougherty Valley High"]]

---

## 第 23 题 [moderate]（上轮结果: cube）

**中文**: 列出 K-12 和 5-17 岁之间入学人数差异超过 30 的学校名称，并提供这些学校的完整街道地址。

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Frpm.enrollmentK12Total",
  "Frpm.enrollmentAges517Total",
  "Schools.schoolsCount"
 ],
 "dimensions": [
  "Frpm.schoolName",
  "Schools.Street"
 ],
 "where(适配器解析前)": "Frpm.enrollmentK12Total - Frpm.enrollmentAges517Total > 30"
}
```

**② Cube 编译出的 SQL**

```（未编译：error_code=600002, error_message=Semantic adapter operation failed: Cube adapter supports equality, IN lists and simple comparisons in `where` (e.g. "）```

**③ 金标 SQL**

```sql
SELECT T1.School, T1.Street FROM schools AS T1 INNER JOIN frpm AS T2 ON T1.CDSCode = T2.CDSCode WHERE T2.`Enrollment (K-12)` - T2.`Enrollment (Ages 5-17)` > 30
```

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube adapter supports equality, IN lists and simple comparisons in `where` (e.g. "Cube.dim = 'v'" / "Cube.dim IN

**金标行(前5)**: [["Alameda County Community", "313 West Winton Avenue"], ["California School for the Deaf-Fremont", "39350 Gallaudet Drive"], ["Alameda High", "2201 Encinal Avenue"], ["Encinal High", "210 Central Avenue"], ["Island High (Continuation)", "1900 Third Street"]]

---

## 第 24 题 [moderate]（上轮结果: cube）

**中文**: 请列出 K-12 阶段符合免费餐食资格比例超过 0.1 且考生成绩大于或等于 1500 的学校名称？

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Frpm.schoolName",
  "Frpm.percentEligibleFreeK12Total",
  "Satscores.NumGE1500Total"
 ],
 "dimensions": [
  "Frpm.schoolName"
 ],
 "where(适配器解析前)": "Frpm.percentEligibleFreeK12Total > 0.1 AND Satscores.NumGE1500Total > 0"
}
```

**② Cube 编译出的 SQL**

```（未编译：error_code=600002, error_message=Semantic adapter operation failed: Cube /sql returned 400: {"error":"Invalid query format: \"havingFilters\" is not a）```

**③ 金标 SQL**

```sql
SELECT T2.`School Name` FROM satscores AS T1 INNER JOIN frpm AS T2 ON T1.cds = T2.CDSCode WHERE CAST(T2.`Free Meal Count (K-12)` AS REAL) / T2.`Enrollment (K-12)` > 0.1 AND T1.NumGE1500 > 0
```

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"error":"Invalid query format: \"havingFilters\" is not allowed"}

**金标行(前5)**: [["Clovis North High"], ["Clovis West High"], ["Buchanan High"], ["Clovis East High"], ["Clovis High"]]

---

## 第 25 题 [moderate]（上轮结果: cube）

**中文**: 列出 Riverside 中 SAT 平均数学分数的平均值大于 400 的学校，这些学校的资助类型是什么？

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Satscores.AvgScrMathTotal",
  "Satscores.satscoresCount"
 ],
 "dimensions": [
  "Schools.School",
  "Schools.FundingType"
 ],
 "where(适配器解析前)": "Schools.County = 'Riverside'"
}
```

**② Cube 编译出的 SQL**

```（未编译：error_code=600002, error_message=Semantic adapter operation failed: Cube /sql returned 400: {"type":"UserError","error":"Can't find join path to join ）```

**③ 金标 SQL**

```sql
SELECT T1.sname, T2.`Charter Funding Type` FROM satscores AS T1 INNER JOIN frpm AS T2 ON T1.cds = T2.CDSCode WHERE T2.`District Name` LIKE 'Riverside%' GROUP BY T1.sname, T2.`Charter Funding Type` HAVING CAST(SUM(T1.AvgScrMath) AS REAL) / COUNT(T1.cds) > 400
```

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"type":"UserError","error":"Can't find join path to join 'Schools', 'Satscores'"}

**金标行(前5)**: [["Arlington High", "None"], ["John W. North High", "None"], ["Martin Luther King Jr. High", "None"], ["Polytechnic High", "None"], ["Ramona High", "None"]]

---

## 第 26 题 [moderate]（上轮结果: cube）

**中文**: 列出蒙特雷高中名称及其完整通信地址，这些高中15-17岁年龄段享受免费或减价餐的人数超过800人？

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Schools.schoolsCount",
  "Frpm.freeMealCountAges517Total"
 ],
 "dimensions": [
  "Frpm.schoolName",
  "Schools.Street",
  "Schools.City",
  "Schools.State",
  "Schools.Zip"
 ],
 "where(适配器解析前)": "Frpm.freeMealCountAges517Total > 800 AND Schools.City = 'Monterey' AND Frpm.highGrade >= 12"
}
```

**② Cube 编译出的 SQL**

```（未编译：error_code=600002, error_message=Semantic adapter operation failed: Cube /sql returned 400: {"error":"Invalid query format: \"havingFilters\" is not a）```

**③ 金标 SQL**

```sql
SELECT T1.`School Name`, T2.Street, T2.City, T2.State, T2.Zip FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T2.County = 'Monterey' AND T1.`Free Meal Count (Ages 5-17)` > 800 AND T1.`School Type` = 'High Schools (Public)'
```

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"error":"Invalid query format: \"havingFilters\" is not allowed"}

**金标行(前5)**: [["Alisal High", "777 Williams Road", "Salinas", "CA", "93905-1907"], ["Everett Alvarez High", "1900 Independence Boulevard", "Salinas", "CA", "93906-5300"], ["North Salinas High", "55 Kip Drive", "Salinas", "CA", "93906-2908"], ["Salinas High", "726 South Mai

---

## 第 27 题 [moderate]（上轮结果: cube）

**中文**: 1991年之后开设或2000年之前关闭的学校，其写作平均分是多少？请列出学校名称及对应的分数。如果有的话，请同时列出这些学校的通信编号。

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Satscores.AvgScrWriteTotal",
  "Schools.Phone"
 ],
 "dimensions": [
  "Schools.School",
  "Schools.Phone"
 ],
 "where(适配器解析前)": "(Schools.OpenDate > '1991-12-31' OR Schools.ClosedDate < '2000-01-01')"
}
```

**② Cube 编译出的 SQL**

```（未编译：error_code=600002, error_message=Semantic adapter operation failed: Cube adapter supports equality, IN lists and simple comparisons in `where` (e.g. "）```

**③ 金标 SQL**

```sql
SELECT T2.School, T1.AvgScrWrite, T2.Phone FROM schools AS T2 LEFT JOIN satscores AS T1 ON T2.CDSCode = T1.cds WHERE strftime('%Y', T2.OpenDate) > '1991' OR strftime('%Y', T2.ClosedDate) < '2000'
```

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube adapter supports equality, IN lists and simple comparisons in `where` (e.g. "Cube.dim = 'v'" / "Cube.dim IN

**金标行(前5)**: [["FAME Public Charter", "None", "None"], ["Envision Academy for Arts & Technology", "None", "(510) 596-8901"], ["Aspire California College Preparatory Academy", "None", "None"], ["Community School for Creative Education", "None", "(510) 686-4131"], ["Yu Ming 

---

## 第 28 题 [challenging]（上轮结果: cube）

**中文**: 考虑由地方资助的学校的 K-12 入学人数与 15-17 岁入学人数之间的平均差异，列出差异高于此平均值的学校名称和 DOC 类型。

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Frpm.enrollmentK12Total",
  "Frpm.enrollmentAges517Total",
  "Frpm.enrollmentK12Total - Frpm.enrollmentAges517Total"
 ],
 "dimensions": [
  "Frpm.schoolName",
  "Frpm.dOC"
 ],
 "where(适配器解析前)": "Frpm.dOC = 'Locally Funded'"
}
```

**② Cube 编译出的 SQL**

```（未编译：error_code=600002, error_message=Semantic adapter operation failed: Cube /sql returned 400: {"error":"Invalid query format: \"measures[2]\" with value）```

**③ 金标 SQL**

```sql
SELECT T2.School, T2.DOC FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T2.FundingType = 'Locally funded' AND (T1.`Enrollment (K-12)` - T1.`Enrollment (Ages 5-17)`) > (SELECT AVG(T3.`Enrollment (K-12)` - T3.`Enrollment (Ages 5-17)`) FROM frpm AS T3 INNER JOIN schools AS T4 ON T3.CDSCode = T4.CDSCode WHERE T4.FundingType = 'Locally funded')
```

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"error":"Invalid query format: \"measures[2]\" with value \"Frpm.enrollmentK12Total - 

**金标行(前5)**: [["Mountain Oaks", "00"], ["Castle Rock", "00"], ["Charter Community School Home Study Academy", "00"], ["Clovis Online Charter", "54"], ["Washington Elementary", "52"]]

---

## 第 29 题 [simple]（上轮结果: cube）

**中文**: 招生人数最多的K-12学校是什么时候开学的？

**① Cube 查询载荷（POST /load 的 JSON）**

```json
{
 "measures": [
  "Frpm.enrollmentK12Total"
 ],
 "dimensions": [
  "Frpm.schoolName",
  "Frpm.OpenDate"
 ],
 "where(适配器解析前)": "Frpm.highGrade = '12'",
 "order_by": [
  "-Frpm.enrollmentK12Total"
 ],
 "limit": 1
}
```

**② Cube 编译出的 SQL**

```（未编译：error_code=600002, error_message=Semantic adapter operation failed: Cube /sql returned 400: {"type":"UserError","error":"'OpenDate' not found for path）```

**③ 金标 SQL**

```sql
SELECT T2.OpenDate FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode ORDER BY T1.`Enrollment (K-12)` DESC LIMIT 1
```

**执行错误**: error_code=600002, error_message=Semantic adapter operation failed: Cube /load returned 400: {"type":"UserError","error":"'OpenDate' not found for path 'Frpm.OpenDate'"}

**金标行(前5)**: [["2006-08-29"]]

---
