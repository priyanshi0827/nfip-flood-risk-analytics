"""Exploratory analysis of the NFIP claims and policy data.

Run AFTER src/build_db.py. Writes findings to outputs/eda_report.md and
figures to outputs/figures/. Everything here is exploratory - the point is to
find out what is actually in the data before deciding what the dashboard
should show.

    python notebooks/01_eda.py
"""
import pathlib
import textwrap

import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "nfip.duckdb"
OUT = ROOT / "outputs"
FIG = OUT / "figures"

NOTES: list[str] = []


def note(text: str) -> None:
    NOTES.append(textwrap.dedent(text).strip())
    print(textwrap.dedent(text).strip() + "\n")


def main() -> int:
    if not DB.exists():
        raise SystemExit("No warehouse. Run: python src/build_db.py")
    FIG.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB), read_only=True)
    q = lambda s: con.execute(s).fetchdf()

    note("# NFIP exploratory analysis\n\nEverything below is computed from the "
         "real OpenFEMA files loaded by `src/build_db.py`.")

    # ---------- 1. Shape and completeness ----------
    shape = q("""
        SELECT count(*) AS claims,
               min(year_of_loss) AS first_year,
               max(year_of_loss) AS last_year,
               sum(CASE WHEN is_error_record THEN 1 ELSE 0 END) AS error_records,
               sum(CASE WHEN is_zero_paid THEN 1 ELSE 0 END) AS zero_paid,
               round(sum(total_paid)/1e9, 2) AS total_paid_bn
        FROM v_claims
    """)
    note(f"## 1. Shape\n\n{shape.to_markdown(index=False)}")

    # How much of each key field is actually populated?
    completeness = q("""
        SELECT 'rated_flood_zone' AS field,
               round(100.0*avg(CASE WHEN rated_flood_zone IS NULL
                    OR rated_flood_zone='' THEN 1.0 ELSE 0 END),2) AS pct_missing
        FROM v_claims
        UNION ALL SELECT 'occupancy_type',
               round(100.0*avg(CASE WHEN occupancy_type IS NULL THEN 1.0 ELSE 0 END),2)
        FROM v_claims
        UNION ALL SELECT 'building_damage',
               round(100.0*avg(CASE WHEN building_damage IS NULL THEN 1.0 ELSE 0 END),2)
        FROM v_claims
        UNION ALL SELECT 'building_coverage',
               round(100.0*avg(CASE WHEN building_coverage IS NULL
                    OR building_coverage=0 THEN 1.0 ELSE 0 END),2)
        FROM v_claims
        UNION ALL SELECT 'payment_date',
               round(100.0*avg(CASE WHEN payment_date IS NULL THEN 1.0 ELSE 0 END),2)
        FROM v_claims
        UNION ALL SELECT 'water_depth',
               round(100.0*avg(CASE WHEN water_depth IS NULL THEN 1.0 ELSE 0 END),2)
        FROM v_claims
        ORDER BY pct_missing DESC
    """)
    note(f"## 2. Field completeness\n\nHow much of each field is unusable. "
         f"Anything above ~30% missing cannot carry a dashboard filter.\n\n"
         f"{completeness.to_markdown(index=False)}")

    # Did anything fall through the code mappings?
    unmapped = q("""
        SELECT occupancy_group, count(*) AS claims,
               round(100.0*count(*)/sum(count(*)) OVER (),2) AS pct
        FROM v_claims GROUP BY 1 ORDER BY claims DESC
    """)
    note(f"## 3. Occupancy mapping coverage\n\nIf 'Unknown' is large, there are "
         f"occupancy codes the mapping does not handle - check the data "
         f"dictionary before trusting any segment cut.\n\n"
         f"{unmapped.to_markdown(index=False)}")

    zones = q("""
        SELECT zone_class, count(*) AS claims,
               round(sum(total_paid)/1e9,2) AS paid_bn,
               round(100.0*sum(total_paid)/sum(sum(total_paid)) OVER (),1) AS pct_paid
        FROM v_claims WHERE NOT is_error_record
        GROUP BY 1 ORDER BY paid_bn DESC
    """)
    note(f"## 4. The headline question: where do the dollars come from?\n\n"
         f"{zones.to_markdown(index=False)}")

    # ---------- 2. Trend ----------
    yearly = q("""
        SELECT year_of_loss, count(*) AS claims,
               round(sum(total_paid)/1e9,3) AS paid_bn
        FROM v_claims
        WHERE NOT is_error_record AND year_of_loss BETWEEN 1978 AND 2025
        GROUP BY 1 ORDER BY 1
    """)
    fig, ax1 = plt.subplots(figsize=(11, 4.5))
    ax1.bar(yearly.year_of_loss, yearly.paid_bn, color="#4C78A8")
    ax1.set_ylabel("Paid losses ($bn, nominal)")
    ax1.set_xlabel("Year of loss")
    ax1.set_title("NFIP paid losses by year of loss (nominal dollars)")
    ax1.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIG / "paid_by_year.png", dpi=130)
    plt.close(fig)

    top_years = yearly.nlargest(8, "paid_bn")
    note(f"## 5. Loss is catastrophe-driven, not steady\n\nThe eight worst loss "
         f"years. If a handful of years dominate, then any 'average year' "
         f"framing in the dashboard is misleading and the design has to show "
         f"the spikes.\n\n{top_years.to_markdown(index=False)}\n\n"
         f"![paid by year](figures/paid_by_year.png)")

    # ---------- 3. Severity distribution ----------
    sev = q("""
        SELECT round(quantile_cont(total_paid,0.50),0) AS p50,
               round(quantile_cont(total_paid,0.75),0) AS p75,
               round(quantile_cont(total_paid,0.90),0) AS p90,
               round(quantile_cont(total_paid,0.99),0) AS p99,
               round(max(total_paid),0) AS max_paid,
               round(avg(total_paid),0) AS mean_paid
        FROM v_claims WHERE total_paid > 0 AND NOT is_error_record
    """)
    note(f"## 6. Severity is heavily skewed\n\nMean vs median tells you whether "
         f"to use averages anywhere in the dashboard.\n\n"
         f"{sev.to_markdown(index=False)}")

    # ---------- 4. Denial reasons ----------
    denial = q("""
        SELECT COALESCE(d.description,'Unmapped: '||c.nonpay_building_code) AS reason,
               count(*) AS claims,
               round(100.0*count(*)/sum(count(*)) OVER (),2) AS pct
        FROM v_claims c LEFT JOIN dim_nonpayment_reason d
          ON d.code = c.nonpay_building_code
        WHERE c.nonpay_building_code IS NOT NULL
        GROUP BY 1 ORDER BY claims DESC LIMIT 15
    """)
    note(f"## 7. Why claims close unpaid\n\nWatch for 'Unmapped' rows - those "
         f"are codes missing from the lookup.\n\n{denial.to_markdown(index=False)}")

    # ---------- 5. Cycle time ----------
    cycle = q("""
        SELECT round(quantile_cont(days_loss_to_payment,0.50),0) AS median_days,
               round(quantile_cont(days_loss_to_payment,0.90),0) AS p90_days,
               round(100.0*avg(CASE WHEN days_loss_to_payment>365 THEN 1.0 ELSE 0 END),1)
                   AS pct_over_year,
               count(*) AS claims_with_dates
        FROM v_claims
        WHERE days_loss_to_payment IS NOT NULL AND NOT is_error_record
    """)
    note(f"## 8. Claim cycle time\n\n{cycle.to_markdown(index=False)}")

    # ---------- 6. Loss ratio, if policies were loaded ----------
    has_mart = con.execute("""
        SELECT count(*) FROM information_schema.tables
        WHERE table_name='mart_loss_ratio'""").fetchone()[0]
    if has_mart:
        orphan = q("""
            SELECT sum(CASE WHEN loss_without_exposure THEN 1 ELSE 0 END) AS orphan_cells,
                   count(*) AS total_cells,
                   round(100.0*sum(CASE WHEN loss_without_exposure
                        THEN incurred_loss ELSE 0 END)/nullif(sum(incurred_loss),0),1)
                        AS pct_loss_unmatched
            FROM mart_loss_ratio
        """)
        note(f"## 9. How well do the two files line up?\n\nShare of losses that "
             f"land in a segment with no matching policy exposure. High values "
             f"mean the aggregate loss ratio is built on shakier ground.\n\n"
             f"{orphan.to_markdown(index=False)}")

        lr = q("""
            SELECT zone_class,
                   sum(policy_count) AS policies,
                   round(sum(written_premium)/1e9,2) AS premium_bn,
                   round(sum(incurred_loss)/1e9,2) AS loss_bn,
                   round(sum(incurred_loss)/nullif(sum(written_premium),0),3) AS loss_ratio
            FROM mart_loss_ratio
            WHERE policy_year BETWEEN 2009 AND 2025 AND NOT loss_without_exposure
            GROUP BY 1 ORDER BY loss_ratio DESC
        """)
        note(f"## 10. Loss ratio by zone class, 2009-2025\n\n"
             f"{lr.to_markdown(index=False)}")
    else:
        note("## 9. Loss ratio\n\nSkipped - policies were not loaded. Re-run "
             "`src/build_db.py` without `--skip-policies`.")

    (OUT / "eda_report.md").write_text("\n\n".join(NOTES) + "\n")
    con.close()
    print(f"\nwrote {OUT/'eda_report.md'} and figures in {FIG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
