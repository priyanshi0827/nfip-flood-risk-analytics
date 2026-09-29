-- Q5: The headline. What share of paid losses sit OUTSIDE the mapped
-- high-risk zone? If a large share of dollars comes from non-SFHA
-- properties, then flood-map zone alone is a weak risk signal - which is
-- the entire commercial argument for supplementing FIRM zones with
-- property-level risk data.
SELECT
    year_of_loss,
    zone_class,
    COUNT(*)                                            AS claims,
    SUM(total_paid)                                     AS paid,
    ROUND(100.0 * SUM(total_paid)
          / SUM(SUM(total_paid)) OVER (PARTITION BY year_of_loss), 1)
                                                        AS pct_of_year_paid
FROM v_claims
WHERE year_of_loss BETWEEN 2009 AND 2025
  AND NOT is_error_record
  AND total_paid > 0
GROUP BY 1, 2
ORDER BY year_of_loss, paid DESC;
