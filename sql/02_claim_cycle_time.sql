-- Q2: How long does a claim take to settle, and where is it slowest?
-- Operational KPI. Uses median, not mean - the tail is extreme.
SELECT
    state,
    zone_class,
    COUNT(*)                                        AS claims,
    ROUND(MEDIAN(days_loss_to_open), 1)             AS median_days_to_open,
    ROUND(MEDIAN(days_loss_to_payment), 1)          AS median_days_to_payment,
    ROUND(QUANTILE_CONT(days_loss_to_payment, 0.90), 1)
                                                    AS p90_days_to_payment,
    ROUND(100.0 * AVG(CASE WHEN days_loss_to_payment > 365
                           THEN 1.0 ELSE 0 END), 1) AS pct_over_one_year
FROM v_claims
WHERE year_of_loss BETWEEN 2009 AND 2025
  AND NOT is_error_record
  AND days_loss_to_payment IS NOT NULL
GROUP BY 1, 2
HAVING COUNT(*) >= 200
ORDER BY median_days_to_payment DESC;
