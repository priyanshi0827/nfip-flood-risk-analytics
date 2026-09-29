# Project context for Claude Code

NFIP flood-insurance analytics. Read this before changing anything.

## What this is

Loss-ratio, claim-cycle-time and coverage-adequacy analysis over FEMA's
National Flood Insurance Program data. Portfolio project aimed at data/risk
analytics roles, specifically LexisNexis Risk Solutions, whose insurance
business sells data that prices flood risk better than FIRM zones alone.

The headline analytical question is `sql/05_sfha_paradox.sql`: what share of
paid losses sits OUTSIDE the mapped high-risk flood zone. If that share is
large, the official flood map is a weak risk signal.

## Non-negotiable rules for this repo

1. **Never invent a number.** Every figure in the README, in any memo, or in
   any resume bullet must come from a query that was actually run against the
   real downloaded files. If the data is not downloaded, the honest answer is
   "not computed yet".
2. **Never fabricate a code lookup.** All code mappings in
   `docs/DATA_DICTIONARY.md` came from FEMA's own metadata endpoint via
   `src/fetch_schema.py`. If a code is unknown, leave it unmapped and let it
   surface as "Unmapped" in output. An earlier version of this project had
   three real bugs caused by guessing at truncated code lists.
3. **State limitations in the open.** The README has a "Known limitations"
   section. If you change the methodology, update it.

## Architecture

```
src/fetch_schema.py    pull live field definitions from FEMA's metadata API
src/download_data.py   resumable bulk parquet download (claims 156MB, policies 3.5GB)
src/build_db.py        DuckDB warehouse
notebooks/01_eda.py    exploratory pass -> outputs/eda_report.md
src/run_analysis.py    run sql/, write outputs/*.csv for Tableau
```

Warehouse objects:
- `fact_claims` - one row per claim, close to source
- `v_claims` - adds derived measures (durations, ratios, `is_error_record`)
- `agg_policy_exposure` - 74.7M policy rows aggregated to the join grain
- `mart_loss_ratio` - losses over premium at the shared grain, ALL years.
  This is the audit surface, not the analysis surface. Do not query it directly.
- `v_loss_ratio` - **query this one.** Pre-filtered to 2009-2025 and to
  segments with matching exposure. The policy file starts in 2009 while claims
  start in 1978, so 41.5% of all incurred loss has no denominator; inside the
  window that drops to 0.17%. A query against the raw table that forgets the
  year filter mixes those in and silently returns a wrong loss ratio.

## The four things that are easy to get wrong

1. **Claims and policies cannot be joined at record level.** FEMA redacts the
   policy key. Loss ratio is computed by aggregating both sides to
   `state x zone_class x occupancy_group x year` and dividing the aggregates.
   That is ecological inference, not record-level truth. `mart_loss_ratio`
   uses a FULL OUTER JOIN so losses in segments with no matching exposure are
   flagged `loss_without_exposure`, not silently dropped. A LEFT JOIN here was
   a real bug that lost ~63% of losses in testing.

2. **`causeOfDamage` is multi-valued.** More than one cause code can appear on
   one claim, so raw values include combinations like `2D`. Split and unnest
   before grouping. A plain GROUP BY returns combination strings.

3. **Loss ratio is `SUM(loss)/SUM(premium)`, never `AVG(loss_ratio)`.**
   Averaging ratios weights a 500-policy cell the same as a 5-million-policy
   one. This applies in SQL and in Tableau calculated fields alike.

4. **Non-payment codes 98 and 99 are administrative corrections**, not
   declined claims. `v_claims.is_error_record` flags them and every analysis
   query excludes them. `04_denial_analysis.sql` keeps them visible on
   purpose - their volume is itself a data-quality metric.

## Gotchas

- `occupancyType` holds both 1-digit legacy and 2-digit Risk Rating 2.0 codes
  in the same column. Both must map to the same groups.
- Claims start 1978, policies do not. Every ratio query is windowed 2009-2025.
- Amounts are nominal, not inflation-adjusted.
- Risk Rating 2.0 changed pricing methodology from Oct 2021, so premium
  before and after is not comparable.
- On a small machine pass `--memory-limit 4GB` to `build_db.py`.
