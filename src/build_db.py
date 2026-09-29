"""Build the analytical warehouse in DuckDB from the OpenFEMA parquet files.

Design note that matters:
FEMA redacts the policy identifier, so a claim CANNOT be joined to its policy
at record level. Anything that needs premium alongside losses (loss ratio,
frequency) is therefore computed by aggregating BOTH sides to a shared grain
- state x flood-zone class x occupancy group x year - and taking the ratio of
the aggregates. That is an approximation, and the README says so out loud.

Usage:
    python src/build_db.py                 # full build
    python src/build_db.py --skip-policies # claims only, much faster
"""
import argparse
import pathlib
import sys
import textwrap

import duckdb

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DB = DATA / "nfip.duckdb"

CLAIMS_PQ = DATA / "NfipClaimsV3.parquet"
POLICIES_PQ = DATA / "NfipPoliciesV3.parquet"
MULTILOSS_PQ = DATA / "NfipMultipleLossProperties.parquet"

# Columns the pipeline genuinely depends on. Validated before anything runs so
# a schema change fails here with a clear message rather than deep in a query.
REQUIRED_CLAIMS = [
    "dateOfLoss", "yearOfLoss", "state", "ratedFloodZone", "occupancyType",
    "amountPaidOnBuildingClaim", "amountPaidOnContentsClaim",
    "amountPaidOnIncreasedCostOfComplianceClaim",
    "buildingDamageAmount", "totalBuildingInsuranceCoverage",
    "nonPaymentReasonBuilding", "causeOfDamage", "openDate",
    "mostRecentPaymentDate", "countyCode", "censusGeoid",
]
REQUIRED_POLICIES = [
    "policyEffectiveDate", "propertyState", "ratedFloodZone", "occupancyType",
    "policyCount", "totalInsurancePremiumOfThePolicy",
    "totalBuildingInsuranceCoverage",
]

# Shared derivation, defined once and reused for both datasets so the join
# grain is guaranteed to be built the same way on each side.
ZONE_CLASS_SQL = """
    CASE
        WHEN {col} IS NULL OR trim({col}) = '' THEN 'Unknown'
        WHEN upper(trim({col})) LIKE 'V%' THEN 'SFHA - Velocity (V)'
        WHEN upper(trim({col})) LIKE 'A%' THEN 'SFHA - Standard (A)'
        WHEN upper(trim({col})) IN ('B','C','X') THEN 'Non-SFHA (B/C/X)'
        WHEN upper(trim({col})) = 'D'   THEN 'Undetermined (D)'
        ELSE 'Other'
    END
"""

# Occupancy codes: 1-digit are legacy, 2-digit are Risk Rating 2.0 era.
# Both appear in the same column and must map to the same groups.
#   1,11 single family      2,12 2-4 unit      3,13,15 5+ unit / condo assoc
#   16   unit in multi-unit 14   mobile home   17 non-res mobile home
#   4,6,18 non-residential  19   non-res unit in multi-unit building
OCCUPANCY_GROUP_SQL = """
    CASE
        WHEN {col} IN (1, 11)         THEN 'Single family'
        WHEN {col} = 16               THEN 'Residential unit in multi-unit'
        WHEN {col} IN (2, 12)         THEN 'Residential 2-4 units'
        WHEN {col} IN (3, 13, 15)     THEN 'Residential 5+ / condo assoc'
        WHEN {col} = 14               THEN 'Mobile / manufactured home'
        WHEN {col} = 17               THEN 'Non-residential mobile home'
        WHEN {col} IN (4, 6, 18, 19)  THEN 'Non-residential'
        ELSE 'Unknown'
    END
"""


def zone_class(col: str) -> str:
    return textwrap.dedent(ZONE_CLASS_SQL.format(col=col)).strip()


def occupancy_group(col: str) -> str:
    return textwrap.dedent(OCCUPANCY_GROUP_SQL.format(col=col)).strip()


def validate(con: duckdb.DuckDBPyConnection, pq: pathlib.Path,
             required: list[str], label: str) -> None:
    if not pq.exists():
        raise SystemExit(
            f"Missing {pq.name}. Run: python src/download_data.py")
    cols = {r[0] for r in con.execute(
        f"DESCRIBE SELECT * FROM read_parquet('{pq.as_posix()}') LIMIT 0"
    ).fetchall()}
    missing = [c for c in required if c not in cols]
    if missing:
        raise SystemExit(
            f"{label}: FEMA schema no longer has these columns: {missing}\n"
            f"Re-run python src/fetch_schema.py and check docs/DATA_DICTIONARY.md"
        )
    print(f"  {label}: {len(cols)} columns present, all required columns found")


def build_lookups(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
    CREATE OR REPLACE TABLE dim_cause_of_damage (code VARCHAR, description VARCHAR);
    INSERT INTO dim_cause_of_damage VALUES
      ('0','Other causes'),
      ('1','Tidal water overflow'),
      ('2','Stream, river, or lake overflow'),
      ('3','Alluvial fan overflow'),
      ('4','Accumulation of rainfall or snowmelt'),
      ('7','Erosion - demolition'),
      ('8','Erosion - removal'),
      ('9','Earth movement, landslide, subsidence, sinkhole'),
      ('A','Closed basin lake'),
      ('B','Expedited handling, no site inspection'),
      ('C','Expedited handling, follow-up site inspection'),
      ('D','Expedited handling, remote adjustment pilot');
    """)
    con.execute("""
    CREATE OR REPLACE TABLE dim_nonpayment_reason (code VARCHAR, description VARCHAR);
    INSERT INTO dim_nonpayment_reason VALUES
      ('01','Claim below deductible'),
      ('02','Seepage'),
      ('03','Backup of drains'),
      ('04','Shrubs not covered'),
      ('05','Sea wall'),
      ('06','Not an actual flood'),
      ('07','Loss in progress'),
      ('08','Failure to pursue claim'),
      ('09','Debris removal only'),
      ('10','Fire'),
      ('11','Fence damage'),
      ('12','Hydrostatic pressure'),
      ('13','Drainage clogged'),
      ('14','Boat piers'),
      ('15','Not insured, damage before policy inception'),
      ('16','Not insured, wind damage'),
      ('17','Erosion type outside flood definition'),
      ('18','Landslide'),
      ('19','Mudflow type outside flood definition'),
      ('20','No demonstrable damage'),
      ('97','Other'),
      ('98','Error - delete claim (no assignment)'),
      ('99','Erroneous assignment');
    """)
    print("  lookups: dim_cause_of_damage, dim_nonpayment_reason")


def build_claims(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"""
    CREATE OR REPLACE TABLE fact_claims AS
    SELECT
        CAST(dateOfLoss AS DATE)                       AS date_of_loss,
        CAST(yearOfLoss AS INTEGER)                    AS year_of_loss,
        upper(trim(state))                             AS state,
        countyCode                                     AS county_fips,
        censusGeoid                                    AS census_geoid,
        nfipCommunityName                              AS community_name,
        upper(trim(ratedFloodZone))                    AS rated_flood_zone,
        {zone_class('ratedFloodZone')}                 AS zone_class,
        CAST(occupancyType AS INTEGER)                 AS occupancy_type,
        {occupancy_group('occupancyType')}             AS occupancy_group,
        floodEvent                                     AS flood_event,
        CAST(causeOfDamage AS VARCHAR)                 AS cause_of_damage_code,
        CAST(waterDepth AS INTEGER)                    AS water_depth,
        CAST(crsClassCode AS INTEGER)                  AS crs_class,

        COALESCE(amountPaidOnBuildingClaim, 0)         AS paid_building,
        COALESCE(amountPaidOnContentsClaim, 0)         AS paid_contents,
        COALESCE(amountPaidOnIncreasedCostOfComplianceClaim, 0) AS paid_icc,
        COALESCE(amountPaidOnBuildingClaim, 0)
          + COALESCE(amountPaidOnContentsClaim, 0)
          + COALESCE(amountPaidOnIncreasedCostOfComplianceClaim, 0) AS total_paid,

        CAST(buildingDamageAmount AS BIGINT)           AS building_damage,
        CAST(totalBuildingInsuranceCoverage AS BIGINT) AS building_coverage,
        CAST(totalContentsInsuranceCoverage AS BIGINT) AS contents_coverage,

        nonPaymentReasonBuilding                       AS nonpay_building_code,
        nonPaymentReasonContents                       AS nonpay_contents_code,

        CAST(openDate AS DATE)                         AS open_date,
        CAST(mostRecentPaymentDate AS DATE)            AS payment_date
    FROM read_parquet('{CLAIMS_PQ.as_posix()}');
    """)

    # Derived measures kept in a view so the base table stays close to source.
    con.execute("""
    CREATE OR REPLACE VIEW v_claims AS
    SELECT *,
        total_paid <= 0                               AS is_zero_paid,
        zone_class LIKE 'SFHA%'                       AS is_sfha,
        -- 98 = error, delete claim; 99 = erroneous assignment. These are
        -- administrative corrections, not real losses. Excluded from every
        -- analysis query rather than deleted, so the count stays auditable.
        COALESCE(nonpay_building_code IN ('98','99'), FALSE)
          OR COALESCE(nonpay_contents_code IN ('98','99'), FALSE)
                                                      AS is_error_record,
        CASE WHEN payment_date IS NOT NULL AND date_of_loss IS NOT NULL
                  AND payment_date >= date_of_loss
             THEN date_diff('day', date_of_loss, payment_date) END
                                                      AS days_loss_to_payment,
        CASE WHEN open_date IS NOT NULL AND date_of_loss IS NOT NULL
                  AND open_date >= date_of_loss
             THEN date_diff('day', date_of_loss, open_date) END
                                                      AS days_loss_to_open,
        CASE WHEN building_coverage > 0
             THEN building_damage::DOUBLE / building_coverage END
                                                      AS damage_to_coverage_ratio,
        CASE WHEN building_coverage > 0 AND building_damage IS NOT NULL
             THEN building_damage >= building_coverage END
                                                      AS coverage_exhausted
    FROM fact_claims;
    """)
    n, lo, hi = con.execute(
        "SELECT count(*), min(year_of_loss), max(year_of_loss) FROM fact_claims"
    ).fetchone()
    err, = con.execute(
        "SELECT count(*) FROM v_claims WHERE is_error_record").fetchone()
    print(f"  fact_claims: {n:,} rows, loss years {lo}-{hi}")
    print(f"    administrative error records flagged (codes 98/99): {err:,}")


def build_policy_exposure(con: duckdb.DuckDBPyConnection) -> None:
    """Aggregate 74.7M policy transactions down to the shared join grain.

    Grain: policy-effective year x state x zone class x occupancy group.
    This is WRITTEN premium by policy year - each renewal is its own
    transaction, which is what we want as the denominator for losses
    occurring in that year. It is not earned premium; see README.
    """
    con.execute(f"""
    CREATE OR REPLACE TABLE agg_policy_exposure AS
    SELECT
        CAST(year(CAST(policyEffectiveDate AS DATE)) AS INTEGER) AS policy_year,
        upper(trim(propertyState))                     AS state,
        {zone_class('ratedFloodZone')}                 AS zone_class,
        {occupancy_group('occupancyType')}             AS occupancy_group,
        SUM(COALESCE(policyCount, 1))                  AS policy_count,
        SUM(COALESCE(totalInsurancePremiumOfThePolicy, 0)) AS written_premium,
        SUM(COALESCE(totalBuildingInsuranceCoverage, 0))   AS building_coverage_exposed
    FROM read_parquet('{POLICIES_PQ.as_posix()}')
    WHERE policyEffectiveDate IS NOT NULL
    GROUP BY 1, 2, 3, 4;
    """)
    n, = con.execute("SELECT count(*) FROM agg_policy_exposure").fetchone()
    print(f"  agg_policy_exposure: {n:,} grain rows")


def build_loss_ratio_mart(con: duckdb.DuckDBPyConnection) -> None:
    # FULL OUTER JOIN, not LEFT. A LEFT JOIN from exposure silently drops any
    # loss that lands in a segment with no matching policy cell that year, and
    # those cells are exactly the interesting ones (data-quality signal, or a
    # zone reclassification between the claim and policy files).
    con.execute("""
    CREATE OR REPLACE TABLE mart_loss_ratio AS
    WITH losses AS (
        SELECT year_of_loss AS policy_year, state, zone_class, occupancy_group,
               count(*)                          AS claim_count,
               SUM(total_paid)                   AS incurred_loss,
               SUM(CASE WHEN total_paid > 0 THEN 1 ELSE 0 END) AS paid_claim_count
        FROM v_claims
        WHERE year_of_loss IS NOT NULL
          AND NOT is_error_record
        GROUP BY 1, 2, 3, 4
    )
    SELECT
        COALESCE(e.policy_year, l.policy_year)           AS policy_year,
        COALESCE(e.state, l.state)                       AS state,
        COALESCE(e.zone_class, l.zone_class)             AS zone_class,
        COALESCE(e.occupancy_group, l.occupancy_group)   AS occupancy_group,
        COALESCE(e.policy_count, 0)                      AS policy_count,
        COALESCE(e.written_premium, 0)                   AS written_premium,
        COALESCE(e.building_coverage_exposed, 0)         AS building_coverage_exposed,
        COALESCE(l.claim_count, 0)                       AS claim_count,
        COALESCE(l.paid_claim_count, 0)                  AS paid_claim_count,
        COALESCE(l.incurred_loss, 0)                     AS incurred_loss,
        e.policy_year IS NULL                            AS loss_without_exposure,
        CASE WHEN COALESCE(e.written_premium, 0) > 0
             THEN COALESCE(l.incurred_loss, 0) / e.written_premium END AS loss_ratio,
        CASE WHEN COALESCE(e.policy_count, 0) > 0
             THEN COALESCE(l.claim_count, 0) * 100.0 / e.policy_count END
                                                         AS claims_per_100_policies,
        CASE WHEN COALESCE(l.paid_claim_count, 0) > 0
             THEN l.incurred_loss / l.paid_claim_count END AS avg_severity
    FROM agg_policy_exposure e
    FULL OUTER JOIN losses l USING (policy_year, state, zone_class, occupancy_group);
    """)
    n, = con.execute("SELECT count(*) FROM mart_loss_ratio").fetchone()
    print(f"  mart_loss_ratio: {n:,} rows")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-policies", action="store_true",
                    help="claims only - skips the 3.5GB / 74.7M-row policies file")
    ap.add_argument("--memory-limit", default="4GB",
                    help="DuckDB memory budget; keep it below the machine's RAM "
                         "(default 4GB, safe on an 8GB Codespace)")
    args = ap.parse_args()

    DATA.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB))
    con.execute("PRAGMA enable_progress_bar")

    # The policies file is ~3.5GB of parquet / 74.7M rows. On a small machine
    # (a 2-core Codespace has 8GB RAM) DuckDB needs an explicit budget and a
    # place to spill, or the aggregation gets OOM-killed. Capping below the
    # box's real RAM and giving it a temp dir makes it spill to disk instead.
    con.execute(f"PRAGMA memory_limit='{args.memory_limit}'")
    con.execute(f"PRAGMA temp_directory='{(DATA / 'duckdb_tmp').as_posix()}'")
    print(f"  memory limit {args.memory_limit}, spilling to data/duckdb_tmp/")

    print("validating schemas:")
    validate(con, CLAIMS_PQ, REQUIRED_CLAIMS, "claims")
    if not args.skip_policies:
        validate(con, POLICIES_PQ, REQUIRED_POLICIES, "policies")

    print("building:")
    build_lookups(con)
    build_claims(con)
    if not args.skip_policies:
        build_policy_exposure(con)
        build_loss_ratio_mart(con)
    else:
        print("  skipped policies, exposure and loss-ratio mart")

    con.close()
    print(f"\nwarehouse ready: {DB}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
