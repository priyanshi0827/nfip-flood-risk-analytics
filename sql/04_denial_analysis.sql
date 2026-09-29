-- Q4: When a claim closes without payment, why?
-- Decoded against FEMA's own reason codes. Separates "policy worked as
-- designed" (below deductible) from "expectation gap" (seepage, drain
-- backup, wind) - the second group is a product and communication problem.
SELECT
    COALESCE(d.description, 'Unmapped code: ' || c.nonpay_building_code)
                                                    AS nonpayment_reason,
    COUNT(*)                                        AS claims,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)
                                                    AS pct_of_denied,
    ROUND(AVG(c.building_damage), 0)                AS avg_assessed_damage,
    COUNT(DISTINCT c.state)                         AS states_seen
FROM v_claims c
LEFT JOIN dim_nonpayment_reason d
       ON d.code = c.nonpay_building_code
WHERE c.nonpay_building_code IS NOT NULL
  -- 98/99 kept deliberately: their volume is a data-quality metric in itself
  AND c.year_of_loss BETWEEN 2009 AND 2025
GROUP BY 1
ORDER BY claims DESC;
