cube(`Frpm`, {
  sql: `SELECT * FROM bird.frpm`,
  joins: {
    Schools: { sql: `${CUBE}."CDSCode" = ${Schools}."CDSCode"`, relationship: `belongsTo` },
  },
  measures: {
    enrollmentK12: { sql: `CAST("Enrollment (K-12)" AS BIGINT)`, type: `sum`, title: `K-12 Enrollment` },
    freeMealK12: { sql: `CAST("Free Meal Count (K-12)" AS BIGINT)`, type: `sum`, title: `K-12 Free Meal Count` },
    frpmEligibleK12: { sql: `CAST("FRPM Count (K-12)" AS BIGINT)`, type: `sum`, title: `K-12 FRPM Count` },
    freeMealRateK12: {
      sql: `COALESCE(SUM(CAST("Free Meal Count (K-12)" AS DOUBLE PRECISION)), 0) / NULLIF(SUM(CAST("Enrollment (K-12)" AS DOUBLE PRECISION)), 0)`,
      type: `number`,
      title: `Free Meal Rate K-12`,
      description: `Eligible free rate for K-12 students: Free Meal Count (K-12) divided by Enrollment (K-12), value range 0-1 decimal. Aliases: eligible free rate, free meal eligibility ratio, 免费餐比例, K-12免费餐资格率. Per-school ratio; also comparable at county level as aggregate SUM/SUM.`,
    },
    enrollmentAges517: { sql: `CAST("Enrollment (Ages 5-17)" AS DOUBLE PRECISION)`, type: `sum`, title: `Enrollment Ages 5-17` },
    freeMealAges517: { sql: `CAST("Free Meal Count (Ages 5-17)" AS BIGINT)`, type: `sum`, title: `Free Meal Count Ages 5-17` },
    freeMealRateAges517: { sql: `COALESCE(SUM(CAST("Free Meal Count (Ages 5-17)" AS DOUBLE PRECISION)), 0) / NULLIF(SUM(CAST("Enrollment (Ages 5-17)" AS DOUBLE PRECISION)), 0)`, type: `number`, title: `Free Meal Rate Ages 5-17` },
    frpmRateAges517: { sql: `COALESCE(SUM(CAST("FRPM Count (Ages 5-17)" AS DOUBLE PRECISION)), 0) / NULLIF(SUM(CAST("Enrollment (Ages 5-17)" AS DOUBLE PRECISION)), 0)`, type: `number`, title: `FRPM Rate Ages 5-17` },
  },
  dimensions: {
    cdsCode: { sql: `"CDSCode"`, type: `string`, primaryKey: true },
    // 行级计算字段：两字段相除（每校自己的率），供"最高/最低/排名"类问题按行排序
    eligibleFreeRateK12: {
      sql: `COALESCE(CAST("Free Meal Count (K-12)" AS DOUBLE PRECISION) / NULLIF(CAST("Enrollment (K-12)" AS DOUBLE PRECISION), 0), -1)`,
      type: `number`,
      title: `Eligible Free Rate K-12 (per school)`,
      description: `Eligible free rate for K-12 students, ROW-LEVEL: Free Meal Count (K-12) / Enrollment (K-12), 0-1 decimal. Aliases: eligible free rate, 免费餐比例, K-12免费餐资格率. NULL when enrollment missing.`,
    },
    countyName: { sql: `"County Name"`, type: `string` },
    districtName: { sql: `"District Name"`, type: `string` },
    schoolName: { sql: `"School Name"`, type: `string` },
    schoolType: { sql: `"School Type"`, type: `string` },
    districtType: { sql: `"District Type"`, type: `string` },
    eduOptionType: { sql: `"Educational Option Type"`, type: `string` },
  },
});
