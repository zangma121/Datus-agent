# BIRD 前 30 题中文对照（california_schools 库）

> 每题附 M5 实验结果（Cube 直接映射路径）。
> 自由 SQL 基线（datus agentic）：28/30 完成，9/28 正确。

## 第 0 题 [simple]

**中文**: Alameda County 的 K-12 学校中，符合条件的免费餐比例最高是多少？

**英文原文**: What is the highest eligible free rate for K-12 students in the schools in Alameda County?

**业务提示(evidence)中译**: K-12 符合条件的免费餐比例 = `Free Meal Count (K-12)` / `Enrollment (K-12)`

**M5 实验状态**: ❌ 查询构造失败
  - 错误: failed: Cube /load returned 400: {"error":"Error: invalid in

## 第 1 题 [moderate]

**中文**: 请列出续读学校中5-17岁学生符合条件的免费餐率最低的三个值。

**英文原文**: Please list the lowest three eligible free rates for students aged 5-17 in continuation schools.

**业务提示(evidence)中译**: 5-17岁学生符合条件的免费餐率 = `Free Meal Count (Ages 5-17)` / `Enrollment (Ages 5-17)`

**M5 实验状态**: ✅ 已执行，答案错误

## 第 2 题 [simple]

**中文**: 请列出弗雷斯诺县教育局所有特许学校的邮政编码。

**英文原文**: Please list the zip code of all the charter schools in Fresno County Office of Education.

**业务提示(evidence)中译**: 特许学校指的是表 fprm 中 `Charter School (Y/N)` = 1 的记录。

**M5 实验状态**: ❌ 查询构造失败
  - 错误: failed: Cube adapter supports equality, IN lists and simple 

## 第 3 题 [simple]

**中文**: K-12 学生中 FRPM 计数最高的学校的完整邮寄街道地址是什么？

**英文原文**: What is the unabbreviated mailing street address of the school with the highest FRPM count for K-12 students?

**M5 实验状态**: ❌ 查询构造失败
  - 错误: failed: Cube /load returned 400: {"error":"Invalid query for

## 第 4 题 [moderate]

**中文**: 请列出2000年1月1日之后开设的直接由特许资金资助的学校电话号码。

**英文原文**: Please list the phone numbers of the direct charter-funded schools that are opened after 2000/1/1.

**业务提示(evidence)中译**: 特许学校指的是 frpm 中 `Charter School (Y/N)` = 1 的学校。

**M5 实验状态**: ✅ 已执行，答案错误

## 第 5 题 [simple]

**中文**: 在SAT考试中数学平均分大于400的学校中，有多少所是纯虚拟学校？

**英文原文**: How many schools with an average score in Math greater than 400 in the SAT test are exclusively virtual?

**业务提示(evidence)中译**: 纯虚拟指的是 Virtual = 'F'

**M5 实验状态**: ❌ 查询构造失败
  - 错误: failed: Cube adapter supports equality, IN lists and simple 

## 第 6 题 [simple]

**中文**: 在SAT考生超过500人的学校中，请列出磁校或提供磁项目的学校。

**英文原文**: Among the schools with the SAT test takers of over 500, please list the schools that are magnet schools or offer a magnet program.

**业务提示(evidence)中译**: 磁校或提供磁项目意味着 `Magnet` = 1

**M5 实验状态**: ❌ 查询构造失败
  - 错误: failed: Cube adapter supports equality, IN lists and simple 

## 第 7 题 [simple]

**中文**: SAT 成绩超过 1500 分的考生人数最多的学校的电话号码是多少？

**英文原文**: What is the phone number of the school that has the highest number of test takers with an SAT score of over 1500?

**M5 实验状态**: ❌ 查询构造失败
  - 错误: failed: Cube /load returned 400: {"type":"UserError","error"

## 第 8 题 [simple]

**中文**: K-12 学生 FRPM 人数最多的学校中，SAT 考生人数是多少？

**英文原文**: What is the number of SAT test takers of the schools with the highest FRPM count for K-12 students?

**M5 实验状态**: ❌ 查询构造失败
  - 错误: failed: Cube /load returned 400: {"error":"Error: invalid in

## 第 9 题 [simple]

**中文**: 在SAT数学平均分超过560的学校中，有多少所是直拨特许资金支持的特许学校？

**英文原文**: Among the schools with the average score in Math over 560 in the SAT test, how many schools are directly charter-funded?

**M5 实验状态**: ✅ 已执行，答案错误

## 第 10 题 [simple]

**中文**: 在SAT考试中阅读平均分最高的学校，其5-17岁学生的FRPM人数是多少？

**英文原文**: For the school with the highest average score in Reading in the SAT test, what is its FRPM count for students aged 5-17?

**M5 实验状态**: ❌ 查询构造失败
  - 错误: failed: Cube /load returned 400: {"error":"Error: column ref

## 第 11 题 [simple]

**中文**: 请列出总入学人数超过500的学校代码。

**英文原文**: Please list the codes of the schools with a total enrollment of over 500.

**业务提示(evidence)中译**: 总入学人数可以用 `Enrollment (K-12)` + `Enrollment (Ages 5-17)` 表示。

**M5 实验状态**: ❌ 查询构造失败
  - 错误: failed: Cube adapter supports equality, IN lists and simple 

## 第 12 题 [moderate]

**中文**: 在SAT优秀率超过0.3的学校中，5-17岁学生符合条件的免费餐率最高是多少？

**英文原文**: Among the schools with an SAT excellence rate of over 0.3, what is the highest eligible free rate for students aged 5-17?

**业务提示(evidence)中译**: 优秀率 = NumGE1500 / NumTstTakr；5-17岁学生符合条件的免费餐率 = `Free Meal Count (Ages 5-17)` / `Enrollment (Ages 5-17)`

**M5 实验状态**: ❌ 查询构造失败
  - 错误: failed: Cube /load returned 400: {"error":"Error: column ref

## 第 13 题 [simple]

**中文**: 请列出SAT优秀率前三的学校的电话号码。

**英文原文**: Please list the phone numbers of the schools with the top 3 SAT excellence rate.

**业务提示(evidence)中译**: 优秀率 = NumGE1500 / NumTstTakr

**M5 实验状态**: ✅ 已执行，答案错误

## 第 14 题 [simple]

**中文**: 按入学人数（5-17岁）从高到低排序，列出前五所学校，并提供它们的NCES学校识别码。

**英文原文**: List the top five schools, by descending order, from the highest to the lowest, the most number of Enrollment (Ages 5-17). Please give their NCES school identification number.

**M5 实验状态**: ❌ 查询构造失败
  - 错误: failed: Cube /load returned 400: {"error":"Error: invalid in

## 第 15 题 [simple]

**中文**: 哪个活跃学区在阅读方面的平均分最高？

**英文原文**: Which active district has the highest average score in Reading?

**M5 实验状态**: ✅ 已执行，答案错误

## 第 16 题 [simple]

**中文**: 合并后的阿拉米达县中，考生人数少于100的学校有多少所？

**英文原文**: How many schools in merged Alameda have number of test takers less than 100?

**M5 实验状态**: ✅ 已执行，答案错误

## 第 17 题 [simple]

**中文**: 按写作平均分对学校进行排名，其中分数大于499，并显示其特许学校编号。

**英文原文**: Rank schools by their average score in Writing where the score is greater than 499, showing their charter numbers.

**业务提示(evidence)中译**: 有效的特许学校编号意味着该编号不为空。

**M5 实验状态**: ✅ 已执行，答案错误

## 第 18 题 [simple]

**中文**: 弗雷斯诺（直接资助）有多少学校的考生人数不超过250人？

**英文原文**: How many schools in Fresno (directly funded) have number of test takers not more than 250?

**M5 实验状态**: ❌ 查询构造失败
  - 错误: failed: Cube adapter supports equality, IN lists and simple 

## 第 19 题 [simple]

**中文**: 数学平均分最高的学校的电话号码是多少？

**英文原文**: What is the phone number of the school that has the highest average score in Math?

**M5 实验状态**: ❌ 查询构造失败
  - 错误: failed: Cube /load returned 400: {"type":"UserError","error"

## 第 20 题 [simple]

**中文**: Amador 有多少所学校的最低年级为 9 且最高年级为 12？

**英文原文**: How many schools in Amador which the Low Grade is 9 and the High Grade is 12?

**M5 实验状态**: 🚫 LLM 判定无法用当前模型回答

## 第 21 题 [simple]

**中文**: 在洛杉矶，有多少所学校的 K-12 阶段免费餐人数超过 500 人，但免费或减价餐人数少于 700 人？

**英文原文**: In Los Angeles how many schools have more than 500 free meals but less than 700 free or reduced price meals for K-12?

**M5 实验状态**: ❌ 查询构造失败
  - 错误: failed: Cube adapter supports equality, IN lists and simple 

## 第 22 题 [simple]

**中文**: 康特拉科斯塔县中考生人数最多的学校是哪所？

**英文原文**: Which school in Contra Costa has the highest number of test takers?

**M5 实验状态**: ✅ 已执行，答案错误

## 第 23 题 [moderate]

**中文**: 列出 K-12 和 5-17 岁之间入学人数差异超过 30 的学校名称，并提供这些学校的完整街道地址。

**英文原文**: List the names of schools with more than 30 difference in enrollements between K-12 and ages 5-17? Please also give the full street adress of the schools.

**业务提示(evidence)中译**: 入学人数差异 = `Enrollment (K-12)` - `Enrollment (Ages 5-17)`

**M5 实验状态**: ❌ 查询构造失败
  - 错误: failed: Cube adapter supports equality, IN lists and simple 

## 第 24 题 [moderate]

**中文**: 请列出 K-12 阶段符合免费餐食资格比例超过 0.1 且考生成绩大于或等于 1500 的学校名称？

**英文原文**: Give the names of the schools with the percent eligible for free meals in K-12 is more than 0.1 and test takers whose test score is greater than or equal to 1500?

**业务提示(evidence)中译**: 符合免费餐食资格比例 = `Free Meal Count (K-12)` / `Total (Enrollment (K-12)`

**M5 实验状态**: ❌ 查询构造失败
  - 错误: failed: Cube adapter supports equality, IN lists and simple 

## 第 25 题 [moderate]

**中文**: 列出 Riverside 中 SAT 平均数学分数的平均值大于 400 的学校，这些学校的资助类型是什么？

**英文原文**: Name schools in Riverside which the average of average math score for SAT is grater than 400, what is the funding type of these schools?

**业务提示(evidence)中译**: 平均数学分数的平均值 = 平均数学分数总和 / 学校数量。

**M5 实验状态**: ❌ 查询构造失败
  - 错误: failed: Cube /load returned 400: {"type":"UserError","error"

## 第 26 题 [moderate]

**中文**: 列出蒙特雷高中名称及其完整通信地址，这些高中15-17岁年龄段享受免费或减价餐的人数超过800人？

**英文原文**: State the names and full communication address of high schools in Monterey which has more than 800 free or reduced price meals for ages 15-17?

**业务提示(evidence)中译**: 完整通信地址应包括街道、城市、州和邮政编码（如有）。

**M5 实验状态**: ❌ 查询构造失败
  - 错误: failed: Cube /load returned 400: {"error":"Error: invalid in

## 第 27 题 [moderate]

**中文**: 1991年之后开设或2000年之前关闭的学校，其写作平均分是多少？请列出学校名称及对应的分数。如果有的话，请同时列出这些学校的通信编号。

**英文原文**: What is the average score in writing for the schools that were opened after 1991 or closed before 2000? List the school names along with the score. Also, list the communication number of the schools if there is any.

**业务提示(evidence)中译**: 通信编号指的是电话号码。

**M5 实验状态**: ❌ 查询构造失败
  - 错误: failed: Cube /load returned 400: {"type":"UserError","error"

## 第 28 题 [challenging]

**中文**: 考虑由地方资助的学校的 K-12 入学人数与 15-17 岁入学人数之间的平均差异，列出差异高于此平均值的学校名称和 DOC 类型。

**英文原文**: Consider the average difference between K-12 enrollment and 15-17 enrollment of schools that are locally funded, list the names and DOC type of schools which has a difference above this average.

**业务提示(evidence)中译**: K-12 入学人数与 15-17 岁入学人数之间的差异可以通过 `Enrollment (K-12)` - `Enrollment (Ages 5-17)` 计算得出。

**M5 实验状态**: ✅ 已执行，答案错误

## 第 29 题 [simple]

**中文**: 招生人数最多的K-12学校是什么时候开学的？

**英文原文**: When did the first-through-twelfth-grade school with the largest enrollment open?

**业务提示(evidence)中译**: K-12 表示从一年级到十二年级

**M5 实验状态**: ❌ 查询构造失败
  - 错误: failed: Cube /load returned 400: {"error":"Invalid query for
