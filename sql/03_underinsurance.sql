-- Q3: How often does damage exceed the coverage the policyholder bought?
-- This is the coverage-adequacy question an underwriter actually asks.
SELECT
    zone_class,
    occupancy_group,
    COUNT(*)                                            AS claims,
    ROUND(MEDIAN(damage_to_coverage_ratio), 3)          AS median_damage_to_coverage,
    ROUND(100.0 * AVG(CASE WHEN coverage_exhausted
                           THEN 1.0 ELSE 0 END), 1)     AS pct_coverage_exhausted,
    ROUND(AVG(building_damage), 0)                      AS avg_building_damage,
    ROUND(AVG(building_coverage), 0)                    AS avg_building_coverage,
    ROUND(AVG(paid_building), 0)                        AS avg_building_paid
FROM v_claims
WHERE building_coverage > 0
  AND NOT is_error_record
  AND building_damage IS NOT NULL
  AND year_of_loss BETWEEN 2009 AND 2025
GROUP BY 1, 2
HAVING COUNT(*) >= 200
ORDER BY pct_coverage_exhausted DESC;
