SELECT
    s.CharterNum,
    sc.AvgScrWrite
FROM satscores sc
JOIN schools s ON sc.cds = s.CDSCode
WHERE sc.AvgScrWrite > 499
    AND s.CharterNum IS NOT NULL
ORDER BY sc.AvgScrWrite DESC
