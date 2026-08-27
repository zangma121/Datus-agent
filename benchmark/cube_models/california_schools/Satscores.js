cube(`Satscores`, {
  sql: `SELECT * FROM bird.satscores`,
  joins: {
    Schools: { sql: `${CUBE}.cds = ${Schools}."CDSCode"`, relationship: `belongsTo` },
  },
  measures: {
    testTakers: { sql: `CAST("NumTstTakr" AS BIGINT)`, type: `sum`, title: `Total SAT Test Takers` },
    avgMath: { sql: `CAST("AvgScrMath" AS DOUBLE PRECISION)`, type: `avg`, title: `Average SAT Math Score` },
    avgRead: { sql: `CAST("AvgScrRead" AS DOUBLE PRECISION)`, type: `avg`, title: `Average SAT Reading Score` },
    avgWrite: { sql: `CAST("AvgScrWrite" AS DOUBLE PRECISION)`, type: `avg`, title: `Average SAT Writing Score` },
    numGE1500: { sql: `CAST("NumGE1500" AS BIGINT)`, type: `sum`, title: `Students scoring >= 1500` },
    excellenceRate: { sql: `COALESCE(SUM(CAST("NumGE1500" AS DOUBLE PRECISION)), 0) / NULLIF(SUM(CAST("NumTstTakr" AS BIGINT)), 0)`, type: `number`, title: `SAT Excellence Rate (>=1500)` },
    enrollment12: { sql: `CAST("enroll12" AS BIGINT)`, type: `sum`, title: `Grade-12 Enrollment` },
  },
  dimensions: {
    cds: { sql: `cds`, type: `string`, primaryKey: true },
    countyName: { sql: `"cname"`, type: `string`, title: `County` },
    districtName: { sql: `"dname"`, type: `string`, title: `District` },
    schoolName: { sql: `"sname"`, type: `string`, title: `School` },
  },
});
