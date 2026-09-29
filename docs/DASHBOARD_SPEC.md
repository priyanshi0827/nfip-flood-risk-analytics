# Tableau Public build spec

Every number in this document was computed from the real OpenFEMA files on
2026-09-29. Use them as sanity checks: if a sheet shows something different,
the sheet is wrong, not the number.

Data sources are the CSVs in `outputs/`. Connect Tableau to that folder as a
text-file source; each CSV is its own connection. No live database needed, so
the workbook travels.

---

## The story the dashboard tells

One argument, in three beats:

1. **23.1% of all NFIP paid losses - $20.68B - are on properties outside the
   mapped high-risk flood zone.** Velocity zones, FEMA's most severe
   designation, account for only 3.2%.
2. **That share is wildly unstable year to year: 5.1% to 52.4%.** It tracks
   peril type. Inland rainfall events (Harvey 2017: 45.9%) flood outside the
   map; coastal surge events (Ian 2022, Helene 2024: 5.1%) hit inside it.
3. **So the zone is a partial signal.** It describes coastal and riverine
   hazard well and rainfall-driven flooding poorly. An underwriter cannot tell
   from the zone alone which kind of exposure they are holding.

That is the argument. Everything on the dashboard should serve it or be cut.

---

## Verification numbers

| Measure | Value |
|---|---|
| Claims | 2,725,989 (1978-2026) |
| Total paid, all years | $89.86B |
| Total paid, 2009-2025 window | $52.35B |
| Administrative error records excluded | 117,748 |
| Non-SFHA share of all-time paid | 23.1% ($20.68B) |
| Median paid claim | $13,146 |
| Mean paid claim | $42,634 |
| Largest single claim | $10.8M |
| Median days loss to payment | 76 |
| p90 days loss to payment | 264 |
| 2005 (Katrina) paid | $17.73B |

Loss ratio by zone class, 2009-2025 (written premium basis):

| Zone class | Policies | Premium | Losses | Loss ratio | Claims/100 policies |
|---|---|---|---|---|---|
| SFHA - Standard (A) | 50.5M | $41.25B | $38.49B | **0.933** | 1.34 |
| Non-SFHA (B/C/X) | 36.3M | $16.59B | $12.19B | **0.735** | 0.71 |
| SFHA - Velocity (V) | 2.2M | $2.98B | $1.48B | **0.496** | 1.02 |

Loss ratio by occupancy, same window:

| Occupancy | Policies | Loss ratio |
|---|---|---|
| Mobile / manufactured home | 215K | **1.055** |
| Single family | 60.9M | 0.937 |
| Residential 5+ / condo assoc | 20.1M | 0.860 |
| Residential 2-4 units | 2.9M | 0.684 |
| Non-residential | 4.6M | 0.579 |

Two findings worth calling out in the memo:

- **Velocity zones are the most profitable segment in the book** (0.496),
  despite being the highest-hazard designation. Pricing over-corrects for V.
- **Mobile and manufactured homes are the only segment losing money** (1.055).

---

## Color

Light mode only - Tableau Public has no dark mode. This palette was validated
for colorblind separation; do not substitute hues.

| Series | Hex | Role |
|---|---|---|
| SFHA - Standard (A) | `#2a78d6` blue | context |
| Non-SFHA (B/C/X) | `#eb6834` orange | **the accent - this is the point** |
| SFHA - Velocity (V) | `#1baf7a` aqua | context |
| Other / unmapped | `#8a8a85` gray | folded tail |

Fold `Unknown` and `Undetermined (D)` into "Other / unmapped" - together they
are 0.9% of paid losses and a fifth and sixth hue would break colorblind
separation.

Rules that are not negotiable:
- Never a dual-axis chart. Two measures of different scale get two sheets.
- Colour follows the zone class, never its rank. Filtering must not repaint.
- Direct-label the Non-SFHA series on every chart it appears in. The orange
  and aqua sit below 3:1 contrast against white, so labels carry identity, not
  colour alone.
- Values, axis labels and legend text stay dark gray. Never colour the text to
  match the series.

---

## Sheets

### 1. KPI row (four stat tiles, not a chart)

Plain text marks, large figures. Left to right:

| Tile | Value | Caption |
|---|---|---|
| Paid losses | $89.9B | 2.73M claims, 1978-2026 |
| Outside the high-risk zone | **23.1%** | $20.68B |
| Median claim | $13,146 | mean $42,634 - skewed |
| Median days to payment | 76 | p90: 264 |

The second tile is the hero. Make it visibly larger than the others.

### 2. Paid losses by year, split by zone class  *(the headline)*

- Source: `05_sfha_paradox.csv`
- Form: stacked column. Columns `year_of_loss`, rows `SUM(paid)`.
- Colour: `zone_class` on Colour using the palette above.
- 2px white gap between stacked segments.
- Annotate 2005, 2012, 2017, 2024 with the event name (Katrina, Sandy, Harvey,
  Helene). The catastrophe spikes are the shape of this data - 2005 alone is
  $17.7B, and the top eight years are 70% of everything.
- Do not add a trend line. There is no trend; there are events.

### 3. Non-SFHA share of paid losses by year  *(the volatility)*

- Source: `05_sfha_paradox.csv`
- Form: single line, orange `#eb6834`, 2px.
- Rows: `pct_of_year_paid` filtered to `zone_class = 'Non-SFHA (B/C/X)'`.
- Add a reference line at the 23.1% all-time average, gray, dashed, labelled.
- Label the extremes directly: 2019 at 52.4%, 2017 at 45.9%, 2022 and 2024 at
  5.1%.
- This sheet is what turns the headline from a statistic into an argument. It
  shows the share is not a constant but a function of peril type.

### 4. Loss ratio by zone class and occupancy

- Source: `01_loss_ratio_by_segment.csv`
- Form: horizontal bar, sorted descending by loss ratio.
- Rows: `occupancy_group`. Columns: `SUM(incurred_loss)/SUM(written_premium)`
  as a calculated field - **not** `AVG(loss_ratio)`, which would average
  ratios and is wrong.
- Reference line at 1.0, labelled "break-even on losses alone".
- Colour: single sequential blue. This is magnitude, not identity.
- Filter: `zone_class`, shown as a control.

Calculated field:
```
Loss Ratio = SUM([Incurred Loss]) / SUM([Written Premium])
```

### 5. Coverage adequacy

- Source: `03_underinsurance.csv`
- Form: horizontal bar of `pct_coverage_exhausted` by `occupancy_group`,
  split by `zone_class`.
- This answers "how often does damage exceed the cover the policyholder
  bought" - the question an underwriter actually asks.

### 6. Why claims close unpaid

- Source: `04_denial_analysis.csv`
- Form: horizontal bar, sorted descending, top 10 reasons.
- Colour: single gray. This is a supporting sheet, not a competing story.
- **Caption it.** "Other" is the single largest category at 21.7%, which is
  itself a data-quality finding: a fifth of unpaid claims carry no usable
  reason code.

---

## Layout

Two dashboards, not one. Cramming six sheets into a single view buries the
argument.

**Dashboard 1 - "Where flood losses actually happen"**
- KPI row across the top
- Sheet 2 (paid by year) full width beneath it
- Sheet 3 (non-SFHA share) full width beneath that
- Caption block, bottom: the three-beat argument in three sentences

**Dashboard 2 - "Portfolio performance"**
- Sheet 4 (loss ratio) left
- Sheet 5 (coverage adequacy) right
- Sheet 6 (denial reasons) full width beneath
- Caption block with the written-premium caveat

Size: 1200 x 900 fixed. Tableau Public renders unpredictably on automatic.

---

## Caveats that must appear on the dashboard

Not in a footnote - visible. They are what make the work credible rather than
naive, and an interviewer will ask.

1. **Claims and policies cannot be joined at record level.** FEMA redacts the
   policy key. Loss ratios are computed by aggregating both sides to
   state x zone class x occupancy group x year and dividing the aggregates.
   That is ecological inference. Within the 2009-2025 window only 0.17% of
   losses fall in segments with no matching exposure, so the approximation
   holds - but it is an approximation.
2. **Written premium, not earned.** Each renewal is its own transaction.
   A true accident-year loss ratio would earn premium across the policy term.
3. **The policy file starts in 2009.** Claims go back to 1978. Every ratio is
   windowed to 2009-2025; the 41.5% of losses with no matching exposure are
   almost entirely pre-2009 and are excluded, not lost.
4. **Nominal dollars.** No inflation adjustment.
5. **Risk Rating 2.0 changed pricing from October 2021.** Premium before and
   after is not generated by the same process.
6. **The NFIP is not a commercial insurer.** Rates are federally set and
   partly subsidised, so a loss ratio here is not the same object as a
   carrier's.

---

## Publishing

Tableau Public makes everything you upload public. There is nothing sensitive
here - it is all federal open data - but check that no local file paths appear
in the data source names before publishing.

Title the workbook: **NFIP Flood Risk Analytics - Where Losses Actually Happen**

Link it from the repo README and from the resume.
