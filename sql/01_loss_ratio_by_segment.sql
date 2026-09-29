-- Q1: Which segments lose money, and is it frequency or severity?
--
-- Reads v_loss_ratio, NOT mart_loss_ratio. The view is pre-filtered to
-- 2009-2025 (the years the policy file covers) and excludes segments with no
-- matching exposure. Querying the raw table without those filters silently
-- mixes in pre-2009 losses that have no denominator - 41.5% of all incurred
-- loss - and produces a loss ratio that is simply wrong.
--
-- Loss ratio is SUM(loss)/SUM(premium), never AVG(loss_ratio). Averaging
-- ratios weights a 500-policy cell the same as a 5-million-policy one.
SELECT
    state,
    zone_class,
    occupancy_group,
    SUM(policy_count)                                       AS policies,
    SUM(written_premium)                                    AS written_premium,
    SUM(incurred_loss)                                      AS incurred_loss,
    ROUND(SUM(incurred_loss) / NULLIF(SUM(written_premium), 0), 3)
                                                            AS loss_ratio,
    ROUND(SUM(claim_count) * 100.0 / NULLIF(SUM(policy_count), 0), 2)
                                                            AS claims_per_100_policies,
    ROUND(SUM(incurred_loss) / NULLIF(SUM(paid_claim_count), 0), 0)
                                                            AS avg_severity
FROM v_loss_ratio
-- 'Unknown' means the rated flood zone was not recorded. Those cells are tiny
-- (1,402 policies in NC) and throw loss ratios above 10, which would sort
-- straight to the top of any chart and mean nothing. They are a data-quality
-- artifact, not a segment. Excluded here; still present in mart_loss_ratio if
-- anyone wants to audit them.
WHERE zone_class NOT IN ('Unknown', 'Undetermined (D)')
GROUP BY 1, 2, 3
HAVING SUM(policy_count) >= 1000   -- suppress thin cells
ORDER BY loss_ratio DESC;
